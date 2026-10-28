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
import android.graphics.Bitmap;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
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
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
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
    private static final int PAGE_IMAGE_REQUEST = 14;
    private static final int EXPORT_PDF_REQUEST = 15;

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private WebView web;
    private TextView offline;
    private LinearLayout navigation;
    private NativeDashboard dashboard;
    private NativeEventScreen eventScreen;
    private NativeExportScreen exportScreen;
    private String exportExperienceId;
    private int exportGeneration;
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
    private final AtomicBoolean snapshotRefreshPending = new AtomicBoolean();
    private boolean offlineVisible;
    private String pendingEventId;

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
        Button deviceStatus = NativeButtons.make(this, "本机", NativeButtons.Role.TONAL);
        deviceStatus.setTextSize(12);
        deviceStatus.setOnClickListener(v -> showDeviceStatus());
        LinearLayout.LayoutParams statusParams = new LinearLayout.LayoutParams(dp(58), dp(48));
        statusParams.rightMargin = dp(6);
        top.addView(deviceStatus, statusParams);
        Button logout = NativeButtons.make(this, "退出", NativeButtons.Role.OUTLINED);
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
                if (request.isForMainFrame() && "https".equals(target.getScheme()) &&
                        SERVER_AUTHORITY.equals(target.getAuthority()) &&
                        target.getPath() != null &&
                        target.getPath().matches("^/my-schedule/experiences/[0-9a-fA-F-]{36}/export$")) {
                    String[] parts = target.getPath().split("/");
                    showNativeExport(parts[parts.length - 2]);
                    return true;
                }
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
                    } else if (dashboard.getVisibility() != View.VISIBLE &&
                            exportScreen.getVisibility() != View.VISIBLE &&
                            eventScreen.getVisibility() != View.VISIBLE) {
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
                showEventFromSnapshot(id);
            }
        });
        dashboard.setVisibility(View.GONE);
        content.addView(dashboard, new FrameLayout.LayoutParams(-1, -1));
        eventScreen = new NativeEventScreen(this, new NativeEventScreen.Actions() {
            @Override public void save(String id, JSONObject payload) { writeEvent(id, payload); }
            @Override public void parse(String rawText) { parseInvitation(rawText); }
            @Override public void delete(String id) { confirmDeleteEvent(id); }
            @Override public void back() {
                activeTab = 1;
                updateNavigation();
                showNative(true);
            }
        });
        eventScreen.setVisibility(View.GONE);
        content.addView(eventScreen, new FrameLayout.LayoutParams(-1, -1));
        exportScreen = new NativeExportScreen(this, new NativeExportScreen.Actions() {
            @Override public void refresh() { loadExportPdf(); }
            @Override public void savePage() { saveExportPage(); }
            @Override public void savePdf() { saveExportPdf(); }
            @Override public void back() { leaveExport(); }
        });
        exportScreen.setVisibility(View.GONE);
        content.addView(exportScreen, new FrameLayout.LayoutParams(-1, -1));
        offline = new TextView(this);
        offline.setTextColor(Color.rgb(25, 40, 70));
        offline.setTextSize(15);
        offline.setPadding(24, 24, 24, 24);
        offline.setMovementMethod(ScrollingMovementMethod.getInstance());
        offline.setVisibility(View.GONE);
        content.addView(offline, new FrameLayout.LayoutParams(-1, -1));
        retry = NativeButtons.make(this, "重试连接", NativeButtons.Role.PRIMARY);
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
            tab.setMinHeight(dp(58));
            tab.setClickable(true);
            tab.setFocusable(true);
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
            pendingEventId = eventId;
            updateNavigation();
        }
        if (BuildConfig.DEBUG && showAcceptanceFixture(getIntent().getStringExtra("acceptance_screen"))) return;
        web.loadUrl(ORIGIN + BASE + "/experiences/plaza");
    }

    private boolean showAcceptanceFixture(String screen) {
        if ("dashboard-home".equals(screen) || "dashboard-calendar".equals(screen) ||
                "dashboard-next-day".equals(screen)) {
            initialHomePending = false;
            activeTab = "dashboard-home".equals(screen) ? 0 : 1;
            updateNavigation();
            try {
                LocalDate today = LocalDate.now(java.time.ZoneId.of("Asia/Shanghai"));
                String events = "{\"events\":[" +
                        "{\"id\":\"acceptance-overnight\",\"title\":\"跨天面试准备\"," +
                        "\"type\":\"personal\",\"start_at\":\"" + today + "T23:00:00+08:00\"," +
                        "\"end_at\":\"" + today.plusDays(1) + "T01:00:00+08:00\",\"completed_at\":null}," +
                        "{\"id\":\"acceptance-done\",\"title\":\"已完成的简历检查\"," +
                        "\"type\":\"personal\",\"start_at\":\"" + today + "T10:00:00+08:00\"," +
                        "\"end_at\":\"" + today + "T11:00:00+08:00\"," +
                        "\"completed_at\":\"" + today + "T11:15:00+08:00\"}]}";
                dashboard.setSnapshot(new JSONObject(events));
            } catch (Exception error) { return false; }
            showNative("dashboard-calendar".equals(screen));
            if ("dashboard-next-day".equals(screen)) {
                dashboard.showCalendar(true);
                dashboard.selectDate(LocalDate.now(java.time.ZoneId.of("Asia/Shanghai")).plusDays(1));
            }
            return true;
        }
        if ("event-detail".equals(screen)) {
            initialHomePending = false;
            activeTab = 2;
            updateNavigation();
            try {
                eventScreen.showEvent(new JSONObject("{\"id\":\"acceptance-event\",\"title\":\"示例面试\"," +
                        "\"type\":\"interview\",\"start_at\":\"2026-10-12T10:00:00+08:00\"," +
                        "\"end_at\":\"2026-10-12T11:00:00+08:00\"}"));
            } catch (Exception error) { return false; }
            showEventScreen();
            return true;
        }
        if ("event".equals(screen) || "event-reminders".equals(screen)) {
            initialHomePending = false;
            activeTab = 2;
            updateNavigation();
            eventScreen.showNew();
            showEventScreen();
            if ("event-reminders".equals(screen))
                eventScreen.post(() -> eventScreen.scrollTo(0, eventScreen.getChildAt(0).getHeight()));
            return true;
        }
        if (!"export".equals(screen) && !"export-page2".equals(screen) &&
                !"export-options".equals(screen)) return false;
        try {
            File fixture = File.createTempFile("acceptance-export-", ".pdf", getCacheDir());
            try (InputStream input = getAssets().open("acceptance-export.pdf");
                 OutputStream output = new FileOutputStream(fixture)) { copy(input, output); }
            initialHomePending = false;
            activeTab = 3;
            updateNavigation();
            web.setVisibility(View.GONE);
            dashboard.setVisibility(View.GONE);
            eventScreen.setVisibility(View.GONE);
            exportScreen.setVisibility(View.VISIBLE);
            navigation.setVisibility(View.VISIBLE);
            exportScreen.open(fixture);
            if ("export-page2".equals(screen)) exportScreen.showPage(2);
            if ("export-options".equals(screen)) exportScreen.showOptions();
            return true;
        } catch (Exception error) {
            Toast.makeText(this, "验收示例无法打开", Toast.LENGTH_LONG).show();
            return false;
        }
    }

    private int dp(float value) {
        return (int) (value * getResources().getDisplayMetrics().density + .5f);
    }

    private RippleDrawable tabBackground(boolean active) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(active ? Color.rgb(221, 245, 243) : Color.TRANSPARENT);
        shape.setCornerRadius(dp(15));
        return new RippleDrawable(ColorStateList.valueOf(0x28007A7F), shape, null);
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
        if (exportScreen.getVisibility() == View.VISIBLE) leaveExport();
        activeTab = index;
        updateNavigation();
        if (index <= 1) {
            showNative(index == 1);
            syncSnapshot(true);
            return;
        }
        if (index == 2) {
            eventScreen.showNew();
            showEventScreen();
            return;
        }
        String[] paths = {BASE + "/experiences", BASE + "/profile"};
        navigateAppPage(paths[index - 3]);
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
        eventScreen.setVisibility(View.GONE);
        exportScreen.setVisibility(View.GONE);
        dashboard.setVisibility(View.VISIBLE);
        dashboard.showCalendar(calendar);
        navigation.setVisibility(View.VISIBLE);
    }

    private void showEventScreen() {
        offlineVisible = false;
        offline.setVisibility(View.GONE);
        retry.setVisibility(View.GONE);
        web.setVisibility(View.GONE);
        dashboard.setVisibility(View.GONE);
        eventScreen.setVisibility(View.VISIBLE);
        exportScreen.setVisibility(View.GONE);
        navigation.setVisibility(View.VISIBLE);
    }

    private void showEventFromSnapshot(String id) {
        JSONArray events = currentSnapshot == null ? null : currentSnapshot.optJSONArray("events");
        if (events != null) for (int i = 0; i < events.length(); i++) {
            JSONObject event = events.optJSONObject(i);
            if (event != null && id.equals(event.optString("id"))) {
                eventScreen.showEvent(event);
                showEventScreen();
                return;
            }
        }
        Toast.makeText(this, "日程正在同步，请稍后重试", Toast.LENGTH_SHORT).show();
        syncSnapshot(true);
    }

    private void confirmDeleteEvent(String id) {
        new AlertDialog.Builder(this).setTitle("删除日程？")
                .setMessage("删除后无法恢复")
                .setNegativeButton("取消", null)
                .setPositiveButton("删除", (dialog, which) -> writeEventRequest("DELETE", id, null))
                .show();
    }

    private void writeEvent(String id, JSONObject payload) {
        writeEventRequest(id == null ? "POST" : "PUT", id, payload);
    }

    private void parseInvitation(String rawText) {
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
                connection = (HttpURLConnection) new URL(ORIGIN + "/api/mobile/v1/events/parse").openConnection();
                connection.setRequestMethod("POST");
                connection.setRequestProperty("Cookie", cookie);
                connection.setRequestProperty("X-CSRF-Token", csrf);
                connection.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
                connection.setConnectTimeout(8000);
                connection.setReadTimeout(10000);
                connection.setDoOutput(true);
                try (OutputStream output = connection.getOutputStream()) {
                    output.write(new JSONObject().put("raw_text", rawText).toString()
                            .getBytes(StandardCharsets.UTF_8));
                }
                if (connection.getResponseCode() != 200)
                    throw new IllegalStateException("邀请解析失败，请检查内容或手动填写");
                JSONObject parsed = new JSONObject(readResponse(connection.getInputStream()));
                runOnUiThread(() -> {
                    eventScreen.applyParsed(parsed, rawText);
                    Toast.makeText(this, "已填入解析结果，请核对后保存", Toast.LENGTH_LONG).show();
                });
            } catch (Exception error) {
                runOnUiThread(() -> Toast.makeText(this, error.getMessage(), Toast.LENGTH_LONG).show());
            } finally {
                if (connection != null) connection.disconnect();
            }
        });
    }

    private void writeEventRequest(String method, String id, JSONObject payload) {
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
                String path = "/api/mobile/v1/events" + (id == null ? "" : "/" + Uri.encode(id));
                connection = (HttpURLConnection) new URL(ORIGIN + path).openConnection();
                connection.setRequestMethod(method);
                connection.setRequestProperty("Cookie", cookie);
                connection.setRequestProperty("X-CSRF-Token", csrf);
                connection.setConnectTimeout(8000);
                connection.setReadTimeout(10000);
                connection.setInstanceFollowRedirects(false);
                if (payload != null) {
                    connection.setDoOutput(true);
                    connection.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
                    try (OutputStream output = connection.getOutputStream()) {
                        output.write(payload.toString().getBytes(StandardCharsets.UTF_8));
                    }
                }
                int status = connection.getResponseCode();
                if (status == 409 && payload != null) {
                    JSONObject conflict = new JSONObject(readResponse(connection.getErrorStream()));
                    JSONArray titles = conflict.optJSONObject("detail").optJSONArray("conflicts");
                    StringBuilder names = new StringBuilder();
                    if (titles != null) for (int i = 0; i < titles.length(); i++) {
                        if (i > 0) names.append("、");
                        names.append(titles.optString(i));
                    }
                    runOnUiThread(() -> new AlertDialog.Builder(this)
                            .setTitle("日程时间重叠")
                            .setMessage(titles == null ? "与已有安排重叠，仍要保存吗？" :
                                    "与 " + names + " 重叠，仍要保存吗？")
                            .setNegativeButton("取消", null)
                            .setPositiveButton("仍保存", (dialog, which) -> {
                                try { payload.put("confirm_overlap", true); }
                                catch (Exception ignored) { }
                                writeEventRequest(method, id, payload);
                            }).show());
                    return;
                }
                int expected = "POST".equals(method) ? 201 : "DELETE".equals(method) ? 204 : 200;
                if (status != expected) throw new IllegalStateException("保存失败（" + status + "），请重试");
                JSONObject saved = payload == null ? null : new JSONObject(readResponse(connection.getInputStream()));
                runOnUiThread(() -> {
                    if (saved != null) try {
                        dashboard.selectDate(OffsetDateTime.parse(saved.getString("start_at"))
                                .atZoneSameInstant(java.time.ZoneId.of("Asia/Shanghai")).toLocalDate());
                    } catch (Exception ignored) { }
                    activeTab = 1;
                    updateNavigation();
                    showNative(true);
                    Toast.makeText(this, "DELETE".equals(method) ? "日程已删除" : "日程已保存", Toast.LENGTH_SHORT).show();
                });
                syncSnapshot(true);
            } catch (Exception error) {
                runOnUiThread(() -> Toast.makeText(this,
                        error.getMessage() == null ? "请求失败，请重试" : error.getMessage(), Toast.LENGTH_LONG).show());
            } finally {
                if (connection != null) connection.disconnect();
            }
        });
    }

    private static String readResponse(InputStream input) throws Exception {
        if (input == null) return "";
        try (InputStream stream = input; ByteArrayOutputStream buffer = new ByteArrayOutputStream()) {
            copy(stream, buffer);
            return buffer.toString(StandardCharsets.UTF_8.name());
        }
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
        if (!snapshotSyncQueued.compareAndSet(false, true)) {
            if (force) snapshotRefreshPending.set(true);
            return;
        }
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
                    if (pendingEventId != null) {
                        String requested = pendingEventId;
                        pendingEventId = null;
                        activeTab = 2;
                        updateNavigation();
                        showEventFromSnapshot(requested);
                    }
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
                if (snapshotRefreshPending.getAndSet(false)) syncSnapshot(true);
            }
        });
    }

    private void signOutLocal() {
        runOnUiThread(() -> {
            exportGeneration++;
            exportExperienceId = null;
            exportScreen.close();
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
        eventScreen.setVisibility(View.GONE);
        exportScreen.setVisibility(View.GONE);
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
        eventScreen.setVisibility(View.GONE);
        exportScreen.setVisibility(View.GONE);
        web.setVisibility(View.VISIBLE);
    }

    private void showNativeExport(String id) {
        exportExperienceId = id;
        activeTab = 3;
        updateNavigation();
        web.setVisibility(View.GONE);
        dashboard.setVisibility(View.GONE);
        eventScreen.setVisibility(View.GONE);
        exportScreen.setVisibility(View.VISIBLE);
        navigation.setVisibility(View.VISIBLE);
        loadExportPdf();
    }

    private void leaveExport() {
        exportGeneration++;
        exportExperienceId = null;
        exportScreen.close();
        showWeb();
    }

    private void loadExportPdf() {
        if (exportExperienceId == null) return;
        String id = exportExperienceId;
        String query = exportScreen.query();
        int generation = ++exportGeneration;
        exportScreen.setLoading();
        String cookie = CookieManager.getInstance().getCookie(ORIGIN);
        if (cookie == null || cookie.isEmpty()) {
            exportScreen.setError("请先登录后导出");
            return;
        }
        executor.execute(() -> {
            HttpURLConnection connection = null;
            File file = null;
            try {
                file = File.createTempFile("experience-export-", ".pdf", getCacheDir());
                String source = ORIGIN + BASE + "/experiences/" + Uri.encode(id) + "/export.pdf?" + query;
                connection = (HttpURLConnection) new URL(source).openConnection();
                connection.setRequestProperty("Cookie", cookie);
                connection.setConnectTimeout(8000);
                connection.setReadTimeout(20000);
                connection.setInstanceFollowRedirects(false);
                if (connection.getResponseCode() != 200 ||
                        connection.getContentType() == null ||
                        !connection.getContentType().startsWith("application/pdf"))
                    throw new IllegalStateException("导出失败，请确认登录状态后重试");
                try (InputStream input = connection.getInputStream();
                     OutputStream output = new FileOutputStream(file)) { copy(input, output); }
                File ready = file;
                runOnUiThread(() -> {
                    if (generation != exportGeneration || exportScreen.getVisibility() != View.VISIBLE) {
                        ready.delete();
                        return;
                    }
                    try { exportScreen.open(ready); }
                    catch (Exception error) {
                        ready.delete();
                        exportScreen.setError("PDF 无法预览，请重试");
                    }
                });
            } catch (Exception error) {
                if (file != null) file.delete();
                runOnUiThread(() -> {
                    if (generation == exportGeneration)
                        exportScreen.setError(error.getMessage() == null ? "导出失败" : error.getMessage());
                });
            } finally {
                if (connection != null) connection.disconnect();
            }
        });
    }

    private void saveExportPage() {
        if (exportScreen.bitmap() == null) return;
        Intent save = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        save.addCategory(Intent.CATEGORY_OPENABLE);
        save.setType("image/png");
        save.putExtra(Intent.EXTRA_TITLE, "面经-第" + exportScreen.pageNumber() + "页.png");
        startActivityForResult(save, PAGE_IMAGE_REQUEST);
    }

    private void saveExportPdf() {
        if (exportScreen.pdfFile() == null) return;
        Intent save = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        save.addCategory(Intent.CATEGORY_OPENABLE);
        save.setType("application/pdf");
        save.putExtra(Intent.EXTRA_TITLE, "面经.pdf");
        startActivityForResult(save, EXPORT_PDF_REQUEST);
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
        } else if (request == PAGE_IMAGE_REQUEST && result == RESULT_OK && data != null) {
            Bitmap bitmap = exportScreen.bitmap();
            if (bitmap != null) try (OutputStream output = getContentResolver().openOutputStream(data.getData())) {
                if (output == null || !bitmap.compress(Bitmap.CompressFormat.PNG, 100, output))
                    throw new IllegalStateException("图片保存失败");
                Toast.makeText(this, "本页图片已保存", Toast.LENGTH_SHORT).show();
            } catch (Exception error) {
                Toast.makeText(this, "图片保存失败", Toast.LENGTH_LONG).show();
            }
        } else if (request == EXPORT_PDF_REQUEST && result == RESULT_OK && data != null) {
            File source = exportScreen.pdfFile();
            if (source != null) executor.execute(() -> {
                try (InputStream input = new java.io.FileInputStream(source);
                     OutputStream output = getContentResolver().openOutputStream(data.getData())) {
                    if (output == null) throw new IllegalStateException();
                    copy(input, output);
                    runOnUiThread(() -> Toast.makeText(this, "PDF 已保存", Toast.LENGTH_SHORT).show());
                } catch (Exception error) {
                    runOnUiThread(() -> Toast.makeText(this, "PDF 保存失败", Toast.LENGTH_LONG).show());
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
        if (exportScreen.getVisibility() == View.VISIBLE) {
            leaveExport();
        } else if (eventScreen.getVisibility() == View.VISIBLE) {
            activeTab = 1;
            updateNavigation();
            showNative(true);
        } else if (offlineVisible) {
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
        exportScreen.close();
        web.destroy();
        executor.shutdown();
        super.onDestroy();
    }

    @Override protected void onResume() {
        super.onResume();
        if (web != null && !initialHomePending && currentSnapshot != null) syncSnapshot(false);
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        String eventId = intent.getStringExtra("event_id");
        if (eventId != null) {
            pendingEventId = eventId;
            syncSnapshot(true);
        }
    }
}
