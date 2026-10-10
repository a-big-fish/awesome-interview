package xyz.hunaochufang.awesomeinterview;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlarmManager;
import android.app.AlertDialog;
import android.app.KeyguardManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.content.res.ColorStateList;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.URLUtil;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import android.window.OnBackInvokedDispatcher;
import android.text.method.ScrollingMovementMethod;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

public final class MainActivity extends Activity {
    private static final String ORIGIN = BuildConfig.SERVER_ORIGIN;
    private static final String SERVER_AUTHORITY = Uri.parse(ORIGIN).getAuthority();
    private static final String BASE = "/my-schedule";
    private static final int FILE_REQUEST = 10;
    private static final int UNLOCK_REQUEST = 11;
    private static final int NOTICE_REQUEST = 12;
    private static final int DOWNLOAD_REQUEST = 13;

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private WebView web;
    private TextView offline;
    private LinearLayout navigation;
    private NativeDashboard dashboard;
    private final TextView[] tabs = new TextView[5];
    private JSONObject currentSnapshot;
    private String sessionCsrf;
    private int activeTab;
    private boolean initialHomePending = true;
    private Button retry;
    private ValueCallback<Uri[]> fileCallback;
    private String downloadUrl;
    private long lastSyncAttempt;
    private final AtomicBoolean snapshotSyncQueued = new AtomicBoolean();
    private boolean offlineVisible;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(246, 248, 252));
        getWindow().setNavigationBarColor(Color.WHITE);
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        if (Build.VERSION.SDK_INT >= 30) getWindow().setDecorFitsSystemWindows(false);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.WHITE);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            int top;
            int bottom;
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(
                        WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars() |
                                WindowInsets.Type.displayCutout());
                top = bars.top;
                bottom = bars.bottom;
            } else {
                // Before API 30 the decor already fits content inside system bars.
                top = 0;
                bottom = 0;
            }
            view.setPadding(0, top, 0, bottom);
            return insets;
        });
        setContentView(root);
        LinearLayout top = new LinearLayout(this);
        top.setGravity(Gravity.CENTER_VERTICAL);
        top.setPadding(dp(16), 0, dp(12), 0);
        top.setBackgroundColor(Color.WHITE);
        top.setElevation(dp(2));
        TextView brand = new TextView(this);
        brand.setText(R.string.app_name);
        brand.setTextColor(Color.rgb(18, 33, 64));
        brand.setTextSize(16);
        brand.setTypeface(null, Typeface.BOLD);
        brand.setOnClickListener(v -> new AlertDialog.Builder(this)
                .setTitle("前往")
                .setItems(new String[]{"面经广场", "我的面试", "网页日程表", "个人设置"},
                        (dialog, which) -> {
                            String[] paths = {BASE + "/experiences/plaza", BASE + "/interviews",
                                    BASE, BASE + "/profile"};
                            activeTab = which == 3 ? 4 : 3;
                            updateNavigation();
                            navigateAppPage(paths[which]);
                        }).show());
        top.addView(brand, new LinearLayout.LayoutParams(0, dp(54), 1));
        Button deviceStatus = new Button(this);
        deviceStatus.setText("本机");
        deviceStatus.setAllCaps(false);
        deviceStatus.setTextSize(12);
        deviceStatus.setOnClickListener(v -> showDeviceStatus());
        top.addView(deviceStatus, new LinearLayout.LayoutParams(dp(58), dp(48)));
        Button logout = new Button(this);
        logout.setText("退出");
        logout.setAllCaps(false);
        logout.setTextSize(12);
        logout.setOnClickListener(v -> web.evaluateJavascript(
                "(function(){let f=document.querySelector('.nav-logout-form');if(f)f.submit()})()", null));
        top.addView(logout, new LinearLayout.LayoutParams(dp(58), dp(48)));
        root.addView(top);
        FrameLayout content = new FrameLayout(this);
        root.addView(content, new LinearLayout.LayoutParams(-1, 0, 1));
        web = new WebView(this);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setCacheMode(android.webkit.WebSettings.LOAD_DEFAULT);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(true);
        web.getSettings().setMixedContentMode(android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        CookieManager.getInstance().setAcceptCookie(true);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri target = request.getUrl();
                if ("https".equals(target.getScheme()) && SERVER_AUTHORITY.equals(target.getAuthority())) return false;
                if ("https".equals(target.getScheme()) || "http".equals(target.getScheme())) {
                    startActivity(new Intent(Intent.ACTION_VIEW, target));
                }
                return true;
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (url.contains("/auth/logout")) {
                    signOutLocal();
                } else if (url.contains("/auth/login")) {
                    if (OfflineStore.prefs(MainActivity.this).contains("user_id")) signOutLocal();
                    navigation.setVisibility(View.GONE);
                    dashboard.setVisibility(View.GONE);
                    web.setVisibility(View.VISIBLE);
                } else if (!url.contains("/auth/login") && url.startsWith(ORIGIN + BASE)) {
                    // Native bottom navigation replaces the page header in the app.
                    view.evaluateJavascript("(function(){let h=document.querySelector('.page-header');if(h)h.style.display='none'})()", null);
                    if (initialHomePending) {
                        initialHomePending = false;
                        showNative(false);
                    } else if (dashboard.getVisibility() != View.VISIBLE) {
                        if (url.contains("/my-schedule/new")) activeTab = 2;
                        else if (url.contains("/my-schedule/experiences")) activeTab = 3;
                        else if (url.contains("/my-schedule/profile")) activeTab = 4;
                        else if (url.contains("/my-schedule/events/")) activeTab = 1;
                        updateNavigation();
                        showWeb();
                    }
                    syncSnapshot(false);
                }
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) offerOffline();
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                    FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent choose = new Intent(Intent.ACTION_GET_CONTENT);
                choose.setType("*/*");
                choose.addCategory(Intent.CATEGORY_OPENABLE);
                startActivityForResult(choose, FILE_REQUEST);
                return true;
            }
        });
        web.setDownloadListener((url, userAgent, disposition, mime, length) -> {
            Uri target = Uri.parse(url);
            if (!"https".equals(target.getScheme()) || !SERVER_AUTHORITY.equals(target.getAuthority())) return;
            downloadUrl = url;
            Intent save = new Intent(Intent.ACTION_CREATE_DOCUMENT);
            save.addCategory(Intent.CATEGORY_OPENABLE);
            save.setType(mime == null || mime.isEmpty() ? "application/octet-stream" : mime);
            save.putExtra(Intent.EXTRA_TITLE, URLUtil.guessFileName(url, disposition, mime));
            startActivityForResult(save, DOWNLOAD_REQUEST);
        });
        content.addView(web, new FrameLayout.LayoutParams(-1, -1));
        dashboard = new NativeDashboard(this, new NativeDashboard.Actions() {
            @Override public void createTodo(LocalDate date) { promptCreateTodo(date); }
            @Override public void toggleTodo(String id) { writeTodo("toggle", id, null, null); }
            @Override public void deleteTodo(String id, String title) {
                new AlertDialog.Builder(MainActivity.this)
                        .setTitle("删除待办？")
                        .setMessage(title)
                        .setNegativeButton("取消", null)
                        .setPositiveButton("删除", (dialog, which) -> writeTodo("delete", id, null, null))
                        .show();
            }
            @Override public void openEvent(String id) {
                activeTab = 2;
                updateNavigation();
                showWeb();
                web.loadUrl(ORIGIN + BASE + "/events/" + Uri.encode(id));
            }
        });
        dashboard.setVisibility(View.GONE);
        content.addView(dashboard, new FrameLayout.LayoutParams(-1, -1));
        offline = new TextView(this);
        offline.setTextColor(Color.rgb(25, 40, 70));
        offline.setTextSize(15);
        offline.setPadding(24, 24, 24, 24);
        offline.setMovementMethod(ScrollingMovementMethod.getInstance());
        offline.setVisibility(View.GONE);
        content.addView(offline, new FrameLayout.LayoutParams(-1, -1));
        retry = new Button(this);
        retry.setText("重试连接");
        retry.setVisibility(View.GONE);
        retry.setOnClickListener(v -> web.reload());
        root.addView(retry);
        navigation = new LinearLayout(this);
        navigation.setGravity(Gravity.CENTER);
        navigation.setPadding(dp(8), dp(5), dp(8), dp(5));
        navigation.setBackgroundColor(Color.WHITE);
        navigation.setElevation(dp(8));
        String[] labels = {"首页", "日历", "添加", "面经", "我的"};
        int[] icons = {R.drawable.nav_home, R.drawable.nav_calendar, R.drawable.nav_add,
                R.drawable.nav_notes, R.drawable.nav_profile};
        for (int i = 0; i < labels.length; i++) {
            final int index = i;
            TextView tab = new TextView(this);
            tab.setText(labels[i]);
            tab.setTextSize(11);
            tab.setGravity(Gravity.CENTER);
            tab.setCompoundDrawablesWithIntrinsicBounds(0, icons[i], 0, 0);
            tab.setCompoundDrawablePadding(dp(4));
            tab.setOnClickListener(v -> selectTab(index));
            tabs[i] = tab;
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(58), 1);
            params.setMargins(dp(2), 0, dp(2), 0);
            navigation.addView(tab, params);
        }
        updateNavigation();
        navigation.setVisibility(View.GONE);
        root.addView(navigation);
        if (Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::handleBack);
        }
        String eventId = getIntent().getStringExtra("event_id");
        if (eventId != null) {
            initialHomePending = false;
            activeTab = 1;
            updateNavigation();
        }
        web.loadUrl(ORIGIN + (eventId == null ? BASE + "/experiences/plaza" : BASE + "/events/" + Uri.encode(eventId)));
    }

    private int dp(float value) {
        return (int) (value * getResources().getDisplayMetrics().density + .5f);
    }

    private GradientDrawable tabBackground(boolean active) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(active ? Color.rgb(221, 245, 243) : Color.TRANSPARENT);
        shape.setCornerRadius(dp(15));
        return shape;
    }

    private void updateNavigation() {
        for (int i = 0; i < tabs.length; i++) {
            TextView tab = tabs[i];
            if (tab == null) continue;
            boolean active = i == activeTab;
            tab.setBackground(tabBackground(active));
            int color = active ? Color.rgb(0, 122, 127) : Color.rgb(92, 108, 122);
            tab.setTextColor(color);
            tab.setCompoundDrawableTintList(ColorStateList.valueOf(color));
            tab.setTypeface(null, active ? Typeface.BOLD : Typeface.NORMAL);
            tab.setContentDescription(tab.getText().toString() +
                    (active ? "，当前页面" : ""));
        }
    }

    private void selectTab(int index) {
        activeTab = index;
        updateNavigation();
        if (index <= 1) {
            showNative(index == 1);
            syncSnapshot(true);
            return;
        }
        String[] paths = {BASE + "/new", BASE + "/experiences", BASE + "/profile"};
        navigateAppPage(paths[index - 2]);
    }

    private void navigateAppPage(String path) {
        boolean cachedRoute = path.equals(BASE) || path.equals(BASE + "/experiences") ||
                path.equals(BASE + "/experiences/plaza");
        if (!cachedRoute || web.getUrl() == null || !web.getUrl().startsWith(ORIGIN + BASE)) {
            showWeb();
            web.loadUrl(ORIGIN + path);
            return;
        }
        String escaped = JSONObject.quote(path);
        web.evaluateJavascript("Boolean(window.awesomeInterviewNavigate && " +
                "window.awesomeInterviewNavigate(" + escaped + "))", result -> {
            if (!"true".equals(result)) web.loadUrl(ORIGIN + path);
            showWeb();
        });
    }

    private void showNative(boolean calendar) {
        offlineVisible = false;
        offline.setVisibility(View.GONE);
        retry.setVisibility(View.GONE);
        web.setVisibility(View.GONE);
        dashboard.setVisibility(View.VISIBLE);
        dashboard.showCalendar(calendar);
        navigation.setVisibility(View.VISIBLE);
    }

    private void promptCreateTodo(LocalDate date) {
        EditText title = new EditText(this);
        title.setSingleLine(true);
        title.setHint("例如：准备面试问题");
        title.setPadding(dp(22), dp(10), dp(22), dp(10));
        new AlertDialog.Builder(this).setTitle("新建待办 · " + date)
                .setView(title)
                .setNegativeButton("取消", null)
                .setPositiveButton("保存", (dialog, which) -> {
                    String value = title.getText().toString().trim();
                    if (value.isEmpty()) {
                        Toast.makeText(this, "请输入待办内容", Toast.LENGTH_SHORT).show();
                        return;
                    }
                    writeTodo("create", null, value, date);
                }).show();
    }

    private void writeTodo(String action, String id, String title, LocalDate date) {
        String cookie = CookieManager.getInstance().getCookie(ORIGIN);
        if (cookie == null || cookie.isEmpty()) {
            Toast.makeText(this, "请先登录", Toast.LENGTH_SHORT).show();
            return;
        }
        executor.execute(() -> {
            HttpURLConnection connection = null;
            try {
                String csrf = currentCsrf(cookie);
                if (csrf == null) throw new IllegalStateException("登录已过期");
                String path = action.equals("create") ? "/api/mobile/v1/todos" :
                        "/api/mobile/v1/todos/" + Uri.encode(id) +
                                (action.equals("delete") ? "" : "/toggle");
                connection = (HttpURLConnection) new URL(ORIGIN + path).openConnection();
                connection.setRequestMethod(action.equals("delete") ? "DELETE" : "POST");
                connection.setRequestProperty("Cookie", cookie);
                connection.setRequestProperty("X-CSRF-Token", csrf);
                connection.setConnectTimeout(8000);
                connection.setReadTimeout(10000);
                connection.setInstanceFollowRedirects(false);
                if (action.equals("create")) {
                    connection.setDoOutput(true);
                    connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8");
                    String form = "title=" + URLEncoder.encode(title, StandardCharsets.UTF_8.name()) +
                            "&due_date=" + date;
                    try (OutputStream output = connection.getOutputStream()) {
                        output.write(form.getBytes(StandardCharsets.UTF_8));
                    }
                }
                int expected = action.equals("create") ? 201 : action.equals("delete") ? 204 : 200;
                if (connection.getResponseCode() != expected)
                    throw new IllegalStateException("保存失败，请重试");
                syncSnapshot(true);
            } catch (Exception error) {
                runOnUiThread(() -> {
                    Toast.makeText(this, error.getMessage(), Toast.LENGTH_LONG).show();
                    dashboard.setSnapshot(currentSnapshot);
                });
            } finally {
                if (connection != null) connection.disconnect();
            }
        });
    }

    private String currentCsrf(String cookie) throws Exception {
        if (sessionCsrf != null) return sessionCsrf;
        HttpURLConnection connection = (HttpURLConnection) new URL(ORIGIN + "/api/mobile/v1/session").openConnection();
        try {
            connection.setRequestProperty("Cookie", cookie);
            connection.setConnectTimeout(8000);
            connection.setReadTimeout(10000);
            connection.setInstanceFollowRedirects(false);
            if (connection.getResponseCode() != 200) return null;
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            try (InputStream input = connection.getInputStream()) { copy(input, buffer); }
            JSONObject session = new JSONObject(buffer.toString(StandardCharsets.UTF_8.name()));
            if (currentSnapshot != null && !session.getString("user_id").equals(currentSnapshot.optString("user_id")))
                return null;
            sessionCsrf = session.getString("csrf_token");
            return sessionCsrf;
        } finally {
            connection.disconnect();
        }
    }

    private void syncSnapshot(boolean force) {
        long now = System.currentTimeMillis();
        if (!force && now - lastSyncAttempt < 30_000) return;
        String cookie = CookieManager.getInstance().getCookie(ORIGIN);
        if (cookie == null || cookie.isEmpty()) return;
        if (!snapshotSyncQueued.compareAndSet(false, true)) return;
        lastSyncAttempt = now;
        executor.execute(() -> {
            HttpURLConnection connection = null;
            try {
                connection = (HttpURLConnection) new URL(ORIGIN + "/api/mobile/v1/snapshot").openConnection();
                connection.setRequestProperty("Cookie", cookie);
                connection.setRequestProperty("Accept", "application/json");
                connection.setConnectTimeout(8000);
                connection.setReadTimeout(10000);
                connection.setInstanceFollowRedirects(false);
                if (connection.getResponseCode() != 200) return;
                String body;
                try (InputStream stream = connection.getInputStream()) {
                    ByteArrayOutputStream buffer = new ByteArrayOutputStream();
                    copy(stream, buffer);
                    body = buffer.toString(StandardCharsets.UTF_8.name());
                }
                JSONObject snapshot = new JSONObject(body);
                if (snapshot.getInt("schema_version") != 1) return;
                String previousOwner = OfflineStore.prefs(this).getString("user_id", null);
                if (previousOwner != null && !previousOwner.equals(snapshot.getString("user_id"))) {
                    ReminderScheduler.cancelAll(this);
                    sessionCsrf = null;
                }
                OfflineStore.save(this, snapshot);
                runOnUiThread(() -> {
                    currentSnapshot = snapshot;
                    dashboard.setSnapshot(snapshot);
                });
                int count = ReminderScheduler.reschedule(this, snapshot);
                if (count > 0 && Build.VERSION.SDK_INT >= 33 &&
                        checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                    runOnUiThread(() -> requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, NOTICE_REQUEST));
                }
                if (count > 0 && Build.VERSION.SDK_INT >= 31) {
                    AlarmManager alarms = (AlarmManager) getSystemService(ALARM_SERVICE);
                    if (!alarms.canScheduleExactAlarms() &&
                            !OfflineStore.prefs(this).getBoolean("exact_prompted", false)) {
                        OfflineStore.prefs(this).edit().putBoolean("exact_prompted", true).apply();
                        runOnUiThread(() -> new AlertDialog.Builder(this)
                                .setTitle("提醒可能延迟")
                                .setMessage("系统尚未允许精确提醒。当前已设置普通系统提醒，触发时间可能延迟。")
                                .setNegativeButton("稍后", null)
                                .setPositiveButton("打开设置", (dialog, which) -> {
                                    try {
                                        startActivity(new Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                                                Uri.parse("package:" + getPackageName())));
                                    } catch (Exception ignored) {
                                        Toast.makeText(this, "请在系统设置中允许精确提醒", Toast.LENGTH_LONG).show();
                                    }
                                }).show());
                    }
                }
            } catch (Exception ignored) {
                // The most recent verified snapshot remains available offline.
            } finally {
                if (connection != null) connection.disconnect();
                snapshotSyncQueued.set(false);
            }
        });
    }

    private void signOutLocal() {
        runOnUiThread(() -> {
            currentSnapshot = null;
            sessionCsrf = null;
            dashboard.setSnapshot(null);
            navigation.setVisibility(View.GONE);
            web.clearCache(true);
            web.clearHistory();
            CookieManager.getInstance().removeAllCookies(null);
        });
        executor.execute(() -> {
            ReminderScheduler.cancelAll(this);
            OfflineStore.clear(this);
        });
    }

    private void offerOffline() {
        runOnUiThread(() -> {
            KeyguardManager guard = (KeyguardManager) getSystemService(KEYGUARD_SERVICE);
            if (!guard.isDeviceSecure()) {
                showOfflineMessage("无法连接服务器。本机未设置锁屏，离线内容暂不可查看。");
                return;
            }
            Intent unlock = guard.createConfirmDeviceCredentialIntent("查看离线内容", "请验证设备身份");
            if (unlock != null) startActivityForResult(unlock, UNLOCK_REQUEST);
        });
    }

    private void displayOffline() {
        try {
            JSONObject snapshot = OfflineStore.load(this);
            StringBuilder content = new StringBuilder("离线只读 · 最近同步：")
                    .append(OfflineStore.prefs(this).getString("synced_at", "未知")).append("\n\n日程\n");
            JSONArray events = snapshot.getJSONArray("events");
            for (int i = 0; i < events.length(); i++) {
                JSONObject item = events.getJSONObject(i);
                content.append("• ").append(item.optString("title")).append("\n  ")
                        .append(item.optString("start_at")).append("\n");
                if (!item.optString("location_text").isEmpty())
                    content.append("  地点：").append(item.optString("location_text")).append("\n");
                if (!item.optString("note").isEmpty())
                    content.append("  备注：").append(item.optString("note")).append("\n");
            }
            content.append("\n待办清单\n");
            JSONArray todos = snapshot.optJSONArray("todos");
            if (todos != null) for (int i = 0; i < todos.length(); i++) {
                JSONObject item = todos.getJSONObject(i);
                content.append(item.isNull("completed_at") ? "□ " : "✓ ")
                        .append(item.optString("title")).append(" · ")
                        .append(item.optString("due_date")).append("\n");
            }
            content.append("\n我的面经\n");
            JSONArray experiences = snapshot.getJSONArray("experiences");
            for (int i = 0; i < experiences.length(); i++) {
                JSONObject item = experiences.getJSONObject(i);
                content.append("• ").append(item.optString("title")).append("\n");
                if (!item.optString("company").isEmpty())
                    content.append("  公司：").append(item.optString("company")).append("\n");
                if (!item.optString("feeling").isEmpty())
                    content.append("  面试感受：").append(item.optString("feeling")).append("\n");
                JSONArray questions = item.optJSONArray("questions");
                if (questions == null) continue;
                for (int j = 0; j < questions.length(); j++) {
                    JSONObject question = questions.getJSONObject(j);
                    content.append("  - ").append(question.optString("question_text")).append("\n");
                    String actual = question.optString("on_site_answer");
                    if (!actual.isEmpty()) content.append("    现场回答：").append(actual).append("\n");
                    String review = question.optString("review_answer");
                    if (!review.isEmpty()) content.append("    复盘答案：").append(review).append("\n");
                    String interviewer = question.optString("interviewer_answer");
                    if (!interviewer.isEmpty()) content.append("    面试官回答：").append(interviewer).append("\n");
                }
            }
            showOfflineMessage(content.toString());
        } catch (Exception error) {
            showOfflineMessage("无法连接服务器，且本机暂无可用的离线内容。");
        }
    }

    private void showOfflineMessage(String message) {
        offlineVisible = true;
        web.setVisibility(View.GONE);
        dashboard.setVisibility(View.GONE);
        offline.setVisibility(View.VISIBLE);
        offline.setText(message);
        retry.setVisibility(View.VISIBLE);
        navigation.setVisibility(View.GONE);
    }

    private void showWeb() {
        offlineVisible = false;
        offline.setVisibility(View.GONE);
        retry.setVisibility(View.GONE);
        navigation.setVisibility(View.VISIBLE);
        dashboard.setVisibility(View.GONE);
        web.setVisibility(View.VISIBLE);
    }

    private void showDeviceStatus() {
        String synced = OfflineStore.prefs(this).getString("synced_at", "尚未同步");
        String notices = Build.VERSION.SDK_INT < 33 ||
                checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
                ? "允许" : "未允许";
        String exact = "系统允许";
        if (Build.VERSION.SDK_INT >= 31) {
            AlarmManager alarms = (AlarmManager) getSystemService(ALARM_SERVICE);
            exact = alarms.canScheduleExactAlarms() ? "系统允许" : "未允许，提醒可能延迟";
        }
        new AlertDialog.Builder(this)
                .setTitle("本机同步与提醒")
                .setMessage("最近同步：" + synced + "\n通知权限：" + notices + "\n精确提醒：" + exact)
                .setNeutralButton("系统权限", (dialog, which) -> startActivity(new Intent(
                        Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        Uri.parse("package:" + getPackageName()))))
                .setNegativeButton("关闭", null)
                .setPositiveButton("重新同步", (dialog, which) -> syncSnapshot(true))
                .show();
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == FILE_REQUEST) {
            if (fileCallback != null) {
                fileCallback.onReceiveValue(result == RESULT_OK && data != null ?
                        WebChromeClient.FileChooserParams.parseResult(result, data) : null);
                fileCallback = null;
            }
        } else if (request == UNLOCK_REQUEST && result == RESULT_OK) {
            displayOffline();
        } else if (request == DOWNLOAD_REQUEST && result == RESULT_OK && data != null && downloadUrl != null) {
            Uri destination = data.getData();
            String source = downloadUrl;
            downloadUrl = null;
            String cookie = CookieManager.getInstance().getCookie(ORIGIN);
            executor.execute(() -> {
                HttpURLConnection connection = null;
                try {
                    connection = (HttpURLConnection) new URL(source).openConnection();
                    connection.setRequestProperty("Cookie", cookie == null ? "" : cookie);
                    connection.setInstanceFollowRedirects(false);
                    if (connection.getResponseCode() != 200) return;
                    try (InputStream input = connection.getInputStream();
                         OutputStream output = getContentResolver().openOutputStream(destination)) {
                        if (output != null) copy(input, output);
                    }
                } catch (Exception ignored) {
                    // The export remains available online for another attempt.
                } finally {
                    if (connection != null) connection.disconnect();
                }
            });
        }
    }

    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results);
        if (request == NOTICE_REQUEST && (results.length == 0 || results[0] != PackageManager.PERMISSION_GRANTED)) {
            Toast.makeText(this, "通知权限未开启，本机不会显示日程提醒", Toast.LENGTH_LONG).show();
        }
    }

    private static void copy(InputStream input, OutputStream output) throws Exception {
        byte[] block = new byte[8192];
        int read;
        while ((read = input.read(block)) >= 0) output.write(block, 0, read);
    }

    @SuppressLint("GestureBackNavigation")
    @Override public void onBackPressed() {
        handleBack();
    }

    private void handleBack() {
        if (offlineVisible) {
            showWeb();
            web.reload();
        } else if (activeTab == 1) {
            activeTab = 0;
            updateNavigation();
            showNative(false);
        } else if (activeTab == 0 && dashboard.getVisibility() == View.VISIBLE) {
            finish();
        } else if (web.canGoBack()) {
            web.goBack();
        } else {
            finish();
        }
    }

    @Override protected void onDestroy() {
        web.destroy();
        executor.shutdown();
        super.onDestroy();
    }

    @Override protected void onResume() {
        super.onResume();
        if (web != null && !initialHomePending && currentSnapshot != null) syncSnapshot(false);
    }
}
