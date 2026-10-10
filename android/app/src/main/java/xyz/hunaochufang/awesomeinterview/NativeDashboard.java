package xyz.hunaochufang.awesomeinterview;

import android.content.Context;
import android.content.res.ColorStateList;
import android.annotation.SuppressLint;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.widget.CheckBox;
import android.widget.FrameLayout;
import android.widget.GridLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.temporal.TemporalAdjusters;
import java.util.ArrayList;
import java.util.List;

/** Native home and calendar backed by the same owner-scoped snapshot as offline reading. */
@SuppressLint("ViewConstructor") // Constructed only in Java with its action callbacks.
final class NativeDashboard extends ScrollView {
    interface Actions {
        void createTodo(LocalDate date);
        void toggleTodo(String id);
        void deleteTodo(String id, String title);
        void openEvent(String id);
    }

    private static final int INK = Color.rgb(23, 41, 61);
    private static final int MUTED = Color.rgb(97, 115, 131);
    private static final int TEAL = Color.rgb(0, 139, 143);
    private static final int PALE = Color.rgb(226, 247, 245);
    private static final int LINE = Color.rgb(222, 231, 235);
    private static final String[] WEEKDAYS = {"一", "二", "三", "四", "五", "六", "日"};
    private static final ZoneId ZONE = ZoneId.of("Asia/Shanghai");
    private final Actions actions;
    private final LinearLayout body;
    private JSONObject snapshot;
    private LocalDate selected = LocalDate.now(ZONE);
    private LocalDate visibleMonth = selected.withDayOfMonth(1);
    private boolean weekMode;
    private boolean calendar;

    NativeDashboard(Context context, Actions actions) {
        super(context);
        this.actions = actions;
        setFillViewport(true);
        setBackgroundColor(Color.rgb(248, 251, 252));
        setVerticalScrollBarEnabled(false);
        body = new LinearLayout(context);
        body.setOrientation(LinearLayout.VERTICAL);
        addView(body, new LayoutParams(-1, -2));
        render();
    }

    void setSnapshot(JSONObject value) {
        snapshot = value;
        render();
    }

    void showCalendar(boolean value) {
        calendar = value;
        render();
        scrollTo(0, 0);
    }

    private int dp(float value) {
        return (int) (value * getResources().getDisplayMetrics().density + .5f);
    }

    private GradientDrawable background(int color, int radius, int stroke) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(color);
        shape.setCornerRadius(dp(radius));
        if (stroke != Color.TRANSPARENT) shape.setStroke(dp(1), stroke);
        return shape;
    }

    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(getContext());
        view.setText(value);
        view.setTextColor(color);
        view.setTextSize(size);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        view.setGravity(Gravity.CENTER_VERTICAL);
        return view;
    }

    private void render() {
        body.removeAllViews();
        if (calendar) renderCalendar();
        else renderHome();
    }

    private void renderHome() {
        LinearLayout hero = new LinearLayout(getContext());
        hero.setOrientation(LinearLayout.VERTICAL);
        hero.setPadding(dp(20), dp(17), dp(20), dp(18));
        hero.setBackgroundColor(TEAL);
        TextView title = text("待办清单", 24, Color.WHITE, true);
        hero.addView(title);
        hero.addView(text(selected.format(DateTimeFormatter.ofPattern("yyyy 年 M 月 d 日")) +
                "  ·  周" + WEEKDAYS[selected.getDayOfWeek().getValue() - 1], 13,
                Color.rgb(218, 249, 245), false));
        addWeekStrip(hero);
        body.addView(hero);

        LinearLayout content = vertical(18, 18, 18, 26);
        body.addView(content);
        LinearLayout heading = new LinearLayout(getContext());
        heading.setGravity(Gravity.CENTER_VERTICAL);
        heading.addView(text("待办事项", 19, INK, true), new LinearLayout.LayoutParams(0, dp(45), 1));
        TextView add = text("＋ 新建", 14, TEAL, true);
        add.setPadding(dp(14), 0, dp(14), 0);
        add.setBackground(background(PALE, 18, Color.TRANSPARENT));
        add.setOnClickListener(v -> actions.createTodo(selected));
        heading.addView(add, new LinearLayout.LayoutParams(-2, dp(36)));
        content.addView(heading);
        TextView hint = text("勾选完成，长按可删除", 12, MUTED, false);
        hint.setPadding(0, 0, 0, dp(10));
        content.addView(hint);
        int count = 0;
        for (JSONObject item : todos()) {
            LocalDate due = date(item.optString("due_date"));
            if (due == null || !(due.equals(selected) ||
                    (selected.equals(LocalDate.now(ZONE)) && due.isBefore(selected) && item.isNull("completed_at")))) continue;
            content.addView(todoRow(item, due.isBefore(selected)));
            count++;
        }
        if (count == 0) content.addView(empty(snapshot == null
                ? "正在同步待办…" : "这一天还没有待办，点击“新建”添加。"));

        TextView agenda = text("当天日程", 19, INK, true);
        agenda.setPadding(0, dp(23), 0, dp(10));
        content.addView(agenda);
        addAgenda(content, selected);
    }

    private void addWeekStrip(LinearLayout parent) {
        LinearLayout strip = new LinearLayout(getContext());
        strip.setPadding(0, dp(18), 0, 0);
        LocalDate monday = selected.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
        for (int i = 0; i < 7; i++) {
            LocalDate day = monday.plusDays(i);
            TextView cell = text("周" + WEEKDAYS[i] + "\n" + day.getDayOfMonth(), 13,
                    day.equals(selected) ? TEAL : Color.WHITE, day.equals(selected));
            cell.setGravity(Gravity.CENTER);
            cell.setMinHeight(dp(58));
            if (day.equals(selected)) cell.setBackground(background(Color.WHITE, 20, Color.TRANSPARENT));
            cell.setOnClickListener(v -> { selected = day; visibleMonth = day.withDayOfMonth(1); render(); });
            strip.addView(cell, new LinearLayout.LayoutParams(0, dp(58), 1));
        }
        parent.addView(strip);
    }

    private View todoRow(JSONObject item, boolean overdue) {
        LinearLayout row = new LinearLayout(getContext());
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(dp(10), dp(6), dp(8), dp(6));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, dp(65));
        params.bottomMargin = dp(8);
        row.setLayoutParams(params);
        row.setBackground(background(Color.WHITE, 14, LINE));
        CheckBox check = new CheckBox(getContext());
        check.setButtonTintList(ColorStateList.valueOf(TEAL));
        boolean done = !item.isNull("completed_at");
        check.setChecked(done);
        check.setContentDescription("完成待办：" + item.optString("title"));
        check.setOnClickListener(v -> actions.toggleTodo(item.optString("id")));
        row.addView(check, new LinearLayout.LayoutParams(dp(44), dp(48)));
        LinearLayout words = new LinearLayout(getContext());
        words.setOrientation(LinearLayout.VERTICAL);
        TextView label = text(item.optString("title"), 15, done ? MUTED : INK, !done);
        if (done) label.setPaintFlags(label.getPaintFlags() | Paint.STRIKE_THRU_TEXT_FLAG);
        label.setMaxLines(2);
        words.addView(label);
        if (overdue) words.addView(text("已逾期", 11, Color.rgb(188, 83, 57), false));
        row.addView(words, new LinearLayout.LayoutParams(0, -2, 1));
        row.setOnLongClickListener(v -> {
            actions.deleteTodo(item.optString("id"), item.optString("title"));
            return true;
        });
        return row;
    }

    private void renderCalendar() {
        LinearLayout header = vertical(18, 18, 18, 16);
        header.setBackgroundColor(Color.WHITE);
        LinearLayout title = new LinearLayout(getContext());
        title.setGravity(Gravity.CENTER_VERTICAL);
        TextView back = text("‹", 28, TEAL, false);
        back.setGravity(Gravity.CENTER);
        back.setOnClickListener(v -> movePeriod(-1));
        title.addView(back, new LinearLayout.LayoutParams(dp(38), dp(42)));
        TextView month = text(visibleMonth.format(DateTimeFormatter.ofPattern("yyyy 年 M 月")),
                21, INK, true);
        month.setGravity(Gravity.CENTER);
        title.addView(month, new LinearLayout.LayoutParams(0, dp(42), 1));
        TextView next = text("›", 28, TEAL, false);
        next.setGravity(Gravity.CENTER);
        next.setOnClickListener(v -> movePeriod(1));
        title.addView(next, new LinearLayout.LayoutParams(dp(38), dp(42)));
        header.addView(title);
        LinearLayout switcher = new LinearLayout(getContext());
        switcher.setBackground(background(Color.rgb(236, 244, 245), 12, Color.TRANSPARENT));
        for (boolean mode : new boolean[]{false, true}) {
            TextView option = text(mode ? "周视图" : "月视图", 14,
                    weekMode == mode ? Color.WHITE : MUTED, weekMode == mode);
            option.setGravity(Gravity.CENTER);
            if (weekMode == mode) option.setBackground(background(TEAL, 11, Color.TRANSPARENT));
            option.setOnClickListener(v -> { weekMode = mode; render(); });
            switcher.addView(option, new LinearLayout.LayoutParams(0, dp(38), 1));
        }
        header.addView(switcher);
        body.addView(header);

        SwipeContainer swipe = new SwipeContainer(getContext());
        swipe.setOrientation(LinearLayout.VERTICAL);
        swipe.setBackgroundColor(Color.WHITE);
        swipe.setPadding(dp(8), dp(6), dp(8), dp(12));
        GridLayout weekdays = new GridLayout(getContext());
        weekdays.setColumnCount(7);
        for (int i = 0; i < 7; i++) {
            TextView day = text("周" + WEEKDAYS[i], 12, MUTED, true);
            day.setGravity(Gravity.CENTER);
            GridLayout.LayoutParams spec = new GridLayout.LayoutParams(
                    GridLayout.spec(0), GridLayout.spec(i, 1f));
            spec.width = 0;
            spec.height = dp(32);
            weekdays.addView(day, spec);
        }
        swipe.addView(weekdays);
        GridLayout grid = new GridLayout(getContext());
        grid.setColumnCount(7);
        LocalDate first = weekMode
                ? selected.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
                : visibleMonth.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
        int cells = weekMode ? 7 : 42;
        for (int i = 0; i < cells; i++) {
            LocalDate day = first.plusDays(i);
            LinearLayout cell = dayCell(day, !weekMode && !day.getMonth().equals(visibleMonth.getMonth()));
            GridLayout.LayoutParams spec = new GridLayout.LayoutParams(
                    GridLayout.spec(i / 7), GridLayout.spec(i % 7, 1f));
            spec.width = 0;
            spec.height = dp(weekMode ? 108 : 63);
            spec.setMargins(dp(1), dp(1), dp(1), dp(1));
            grid.addView(cell, spec);
        }
        swipe.addView(grid);
        body.addView(swipe);
        LinearLayout agenda = vertical(18, 20, 18, 30);
        TextView heading = text(selected.format(DateTimeFormatter.ofPattern("M 月 d 日")) + " · 当天安排", 18, INK, true);
        agenda.addView(heading);
        addAgenda(agenda, selected);
        body.addView(agenda);
    }

    private LinearLayout dayCell(LocalDate day, boolean outside) {
        LinearLayout cell = new LinearLayout(getContext());
        cell.setOrientation(LinearLayout.VERTICAL);
        cell.setPadding(dp(3), dp(4), dp(2), 0);
        cell.setBackground(background(day.equals(selected) ? PALE : Color.WHITE, 5,
                day.equals(selected) ? TEAL : LINE));
        TextView number = text(Integer.toString(day.getDayOfMonth()), 14,
                outside ? Color.rgb(171, 184, 190) : day.equals(selected) ? TEAL : INK,
                day.equals(selected));
        cell.addView(number);
        int events = 0;
        for (JSONObject item : events()) {
            if (!day.equals(eventDate(item))) continue;
            events++;
            if (weekMode && events <= 2) {
                TextView label = text(item.optString("title"), 10, Color.WHITE, false);
                label.setSingleLine(true);
                label.setPadding(dp(2), 0, dp(2), 0);
                label.setBackground(background(eventColor(item.optString("type")), 3, Color.TRANSPARENT));
                LinearLayout.LayoutParams layout = new LinearLayout.LayoutParams(-1, dp(19));
                layout.topMargin = dp(3);
                cell.addView(label, layout);
            }
        }
        if (!weekMode && events > 0) cell.addView(text(events + " 项", 10, TEAL, true));
        cell.setOnClickListener(v -> {
            selected = day;
            visibleMonth = day.withDayOfMonth(1);
            render();
        });
        return cell;
    }

    private void addAgenda(LinearLayout parent, LocalDate day) {
        int count = 0;
        for (JSONObject item : events()) {
            if (!day.equals(eventDate(item))) continue;
            count++;
            LinearLayout line = new LinearLayout(getContext());
            line.setGravity(Gravity.CENTER_VERTICAL);
            line.setPadding(dp(12), dp(11), dp(12), dp(11));
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
            params.topMargin = dp(8);
            line.setLayoutParams(params);
            line.setBackground(background(Color.WHITE, 12, LINE));
            View stripe = new View(getContext());
            stripe.setBackground(background(eventColor(item.optString("type")), 4, Color.TRANSPARENT));
            line.addView(stripe, new LinearLayout.LayoutParams(dp(4), dp(38)));
            LinearLayout words = new LinearLayout(getContext());
            words.setPadding(dp(12), 0, 0, 0);
            words.setOrientation(LinearLayout.VERTICAL);
            words.addView(text(item.optString("title"), 15, INK, true));
            String start = item.optString("start_at");
            words.addView(text(start.length() >= 16 ? start.substring(11, 16) : "查看详情", 12, MUTED, false));
            line.addView(words, new LinearLayout.LayoutParams(0, -2, 1));
            line.setOnClickListener(v -> actions.openEvent(item.optString("id")));
            parent.addView(line);
        }
        if (count == 0) parent.addView(empty(snapshot == null
                ? "正在同步日程…" : "这一天没有日程。"));
    }

    private TextView empty(String message) {
        TextView view = text(message, 14, MUTED, false);
        view.setPadding(dp(14), dp(16), dp(14), dp(16));
        view.setBackground(background(Color.WHITE, 12, LINE));
        return view;
    }

    private LinearLayout vertical(int left, int top, int right, int bottom) {
        LinearLayout view = new LinearLayout(getContext());
        view.setOrientation(LinearLayout.VERTICAL);
        view.setPadding(dp(left), dp(top), dp(right), dp(bottom));
        return view;
    }

    private void movePeriod(int direction) {
        if (weekMode) selected = selected.plusWeeks(direction);
        else selected = visibleMonth.plusMonths(direction).withDayOfMonth(1);
        visibleMonth = selected.withDayOfMonth(1);
        render();
    }

    private List<JSONObject> events() { return items("events"); }
    private List<JSONObject> todos() { return items("todos"); }

    private List<JSONObject> items(String key) {
        List<JSONObject> result = new ArrayList<>();
        JSONArray array = snapshot == null ? null : snapshot.optJSONArray(key);
        if (array != null) for (int i = 0; i < array.length(); i++) {
            JSONObject item = array.optJSONObject(i);
            if (item != null) result.add(item);
        }
        return result;
    }

    private static LocalDate date(String value) {
        try { return LocalDate.parse(value); } catch (Exception ignored) { return null; }
    }

    private static LocalDate eventDate(JSONObject item) {
        try {
            return OffsetDateTime.parse(item.optString("start_at")).atZoneSameInstant(ZONE).toLocalDate();
        } catch (Exception ignored) {
            String value = item.optString("start_at");
            return value.length() >= 10 ? date(value.substring(0, 10)) : null;
        }
    }

    private static int eventColor(String type) {
        switch (type) {
            case "interview": return Color.rgb(70, 99, 218);
            case "exam": return Color.rgb(202, 100, 62);
            case "course": return Color.rgb(124, 91, 176);
            case "meeting": return Color.rgb(0, 139, 143);
            default: return Color.rgb(91, 112, 128);
        }
    }

    @SuppressLint("ViewConstructor")
    private final class SwipeContainer extends LinearLayout {
        private float downX;
        private float downY;

        SwipeContainer(Context context) {
            super(context);
            setClickable(true);
            setContentDescription("左右滑动切换月视图和周视图");
        }

        @Override public boolean onInterceptTouchEvent(MotionEvent event) {
            if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
                downX = event.getX();
                downY = event.getY();
            } else if (event.getActionMasked() == MotionEvent.ACTION_MOVE &&
                    Math.abs(event.getX() - downX) > dp(25) &&
                    Math.abs(event.getX() - downX) > Math.abs(event.getY() - downY) * 1.2f) {
                return true;
            }
            return super.onInterceptTouchEvent(event);
        }

        @Override public boolean onTouchEvent(MotionEvent event) {
            if (event.getActionMasked() == MotionEvent.ACTION_UP) {
                float dx = event.getX() - downX;
                if (Math.abs(dx) > dp(60)) {
                    weekMode = !weekMode;
                    post(NativeDashboard.this::render);
                    return true;
                }
                if (Math.abs(dx) < dp(10) && Math.abs(event.getY() - downY) < dp(10))
                    return performClick();
                return true;
            }
            return true;
        }

        @Override public boolean performClick() {
            super.performClick();
            weekMode = !weekMode;
            post(NativeDashboard.this::render);
            return true;
        }
    }
}
