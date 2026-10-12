package xyz.hunaochufang.awesomeinterview;

import android.app.DatePickerDialog;
import android.app.TimePickerDialog;
import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;

/** Native event detail and manual editor backed by the personal schedule API. */
final class NativeEventScreen extends ScrollView {
    interface Actions {
        void save(String eventId, JSONObject payload);
        void parse(String rawText);
        void delete(String eventId);
        void back();
    }

    private static final ZoneId ZONE = ZoneId.of("Asia/Shanghai");
    private static final String[] TYPES = {"面试", "笔试", "课程", "招聘活动", "会议", "个人事项"};
    private static final String[] VALUES = {"interview", "exam", "course", "recruiting", "meeting", "personal"};
    private final Actions actions;
    private final LinearLayout body;
    private JSONObject event;
    private String eventId;
    private ZonedDateTime start;
    private ZonedDateTime end;
    private TextView startLabel;
    private TextView endLabel;
    private String rawInvitation;

    NativeEventScreen(Context context, Actions actions) {
        super(context);
        this.actions = actions;
        setFillViewport(true);
        setBackgroundColor(Color.rgb(248, 251, 252));
        body = new LinearLayout(context);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(20), dp(20), dp(20), dp(36));
        addView(body, new LayoutParams(-1, -2));
    }

    String editingEventId() { return eventId; }

    void showNew() {
        event = null;
        eventId = null;
        rawInvitation = null;
        start = ZonedDateTime.now(ZONE).plusHours(1).withMinute(0).withSecond(0).withNano(0);
        end = start.plusHours(1);
        showForm(null);
    }

    void showEvent(JSONObject value) {
        event = value;
        eventId = value.optString("id");
        rawInvitation = null;
        renderDetail();
    }

    void applyParsed(JSONObject value, String rawText) {
        rawInvitation = rawText;
        showForm(value);
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + .5f);
    }

    private GradientDrawable background(int color) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(color);
        shape.setCornerRadius(dp(12));
        return shape;
    }

    private TextView text(String value, int size, boolean bold) {
        TextView view = new TextView(getContext());
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(Color.rgb(25, 40, 65));
        if (bold) view.setTypeface(null, Typeface.BOLD);
        return view;
    }

    private void addHeading(String title) {
        body.removeAllViews();
        TextView heading = text(title, 24, true);
        heading.setPadding(0, 0, 0, dp(20));
        body.addView(heading);
    }

    private void addLabel(String label) {
        TextView view = text(label, 14, true);
        view.setPadding(0, dp(14), 0, dp(6));
        body.addView(view);
    }

    private EditText field(String label, String value) {
        addLabel(label);
        EditText input = new EditText(getContext());
        input.setSingleLine(true);
        input.setText(value);
        input.setTextSize(16);
        input.setPadding(dp(12), dp(10), dp(12), dp(10));
        input.setBackground(background(Color.WHITE));
        body.addView(input, new LinearLayout.LayoutParams(-1, dp(52)));
        return input;
    }

    private Button button(String label, boolean primary) {
        Button view = new Button(getContext());
        view.setText(label);
        view.setAllCaps(false);
        view.setTextColor(primary ? Color.WHITE : Color.rgb(35, 75, 180));
        view.setBackground(background(primary ? Color.rgb(36, 88, 255) : Color.WHITE));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, dp(50));
        params.topMargin = dp(16);
        body.addView(view, params);
        return view;
    }

    private ZonedDateTime parseDate(String value, ZonedDateTime fallback) {
        try { return OffsetDateTime.parse(value).atZoneSameInstant(ZONE); }
        catch (Exception ignored) { return fallback; }
    }

    private String displayDate(ZonedDateTime value) {
        return value.format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"));
    }

    private void pickDateTime(boolean starting) {
        ZonedDateTime current = starting ? start : end;
        new DatePickerDialog(getContext(), (picker, year, month, day) ->
                new TimePickerDialog(getContext(), (clock, hour, minute) -> {
                    ZonedDateTime picked = LocalDateTime.of(year, month + 1, day, hour, minute).atZone(ZONE);
                    if (starting) {
                        start = picked;
                        end = picked.plusHours(1);
                    } else end = picked;
                    startLabel.setText(displayDate(start));
                    endLabel.setText(displayDate(end));
                }, current.getHour(), current.getMinute(), true).show(),
                current.getYear(), current.getMonthValue() - 1, current.getDayOfMonth()).show();
    }

    private void showForm(JSONObject initial) {
        if (initial != null) {
            start = parseDate(initial.optString("start_at"), ZonedDateTime.now(ZONE));
            end = parseDate(initial.optString("end_at"), start.plusHours(1));
        }
        addHeading(eventId == null ? "添加日程" : "编辑日程");
        LinearLayout invitationGroup = null;
        if (eventId == null) {
            invitationGroup = new LinearLayout(getContext());
            invitationGroup.setOrientation(LinearLayout.VERTICAL);
            body.addView(invitationGroup);
            EditText invitation = field("粘贴面试邀请（可选）", rawInvitation == null ? "" : rawInvitation);
            invitation.setSingleLine(false);
            invitation.setMinLines(3);
            invitation.setGravity(Gravity.TOP);
            invitation.getLayoutParams().height = dp(116);
            Button parse = button("解析邀请并填入下方", false);
            parse.setOnClickListener(v -> {
                String raw = invitation.getText().toString().trim();
                if (raw.isEmpty()) invitation.setError("请先粘贴邀请内容");
                else actions.parse(raw);
            });
            int groupIndex = body.indexOfChild(invitationGroup);
            for (int i = 0; i < 3; i++) {
                View child = body.getChildAt(groupIndex + 1);
                body.removeView(child);
                invitationGroup.addView(child);
            }
        }
        EditText title = field("标题", initial == null ? "" : initial.optString("title"));
        addLabel("类型");
        Spinner type = new Spinner(getContext());
        type.setAdapter(new ArrayAdapter<>(getContext(), android.R.layout.simple_spinner_dropdown_item, TYPES));
        String initialType = initial == null ? "interview" : initial.optString("type", "interview");
        for (int i = 0; i < VALUES.length; i++) if (VALUES[i].equals(initialType)) type.setSelection(i);
        body.addView(type, new LinearLayout.LayoutParams(-1, dp(52)));
        addLabel("开始时间");
        startLabel = text(displayDate(start), 16, false);
        startLabel.setGravity(Gravity.CENTER_VERTICAL);
        startLabel.setPadding(dp(12), 0, dp(12), 0);
        startLabel.setBackground(background(Color.WHITE));
        startLabel.setOnClickListener(v -> pickDateTime(true));
        body.addView(startLabel, new LinearLayout.LayoutParams(-1, dp(52)));
        addLabel("结束时间");
        endLabel = text(displayDate(end), 16, false);
        endLabel.setGravity(Gravity.CENTER_VERTICAL);
        endLabel.setPadding(dp(12), 0, dp(12), 0);
        endLabel.setBackground(background(Color.WHITE));
        endLabel.setOnClickListener(v -> pickDateTime(false));
        body.addView(endLabel, new LinearLayout.LayoutParams(-1, dp(52)));
        EditText position = field("应聘岗位（面试可选）", initial == null ? "" : initial.optString("position"));
        View positionLabel = body.getChildAt(body.getChildCount() - 2);
        LinearLayout finalInvitationGroup = invitationGroup;
        type.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(android.widget.AdapterView<?> parent, View view, int selected, long id) {
                position.setVisibility(selected == 0 ? View.VISIBLE : View.GONE);
                positionLabel.setVisibility(selected == 0 ? View.VISIBLE : View.GONE);
                if (finalInvitationGroup != null)
                    finalInvitationGroup.setVisibility(selected == 0 ? View.VISIBLE : View.GONE);
            }
            @Override public void onNothingSelected(android.widget.AdapterView<?> parent) { }
        });
        EditText location = field("地点", initial == null ? "" : initial.optString("location_text"));
        EditText note = field("备注", initial == null ? "" : initial.optString("note"));
        addLabel("系统提醒（默认关闭）");
        int[] offsets = {10, 60, 1440};
        String[] reminders = {"提前 10 分钟", "提前 1 小时", "提前 1 天"};
        CheckBox[] checks = new CheckBox[3];
        JSONArray saved = initial == null ? null : initial.optJSONArray("reminder_offsets_minutes");
        for (int i = 0; i < checks.length; i++) {
            checks[i] = new CheckBox(getContext());
            checks[i].setText(reminders[i]);
            if (saved != null) for (int j = 0; j < saved.length(); j++)
                if (saved.optInt(j) == offsets[i]) checks[i].setChecked(true);
            body.addView(checks[i]);
        }
        button("保存日程", true).setOnClickListener(v -> {
            if (title.getText().toString().trim().isEmpty() || !end.isAfter(start)) {
                title.setError("请填写标题，并确认结束时间晚于开始时间");
                return;
            }
            try {
                JSONObject payload = new JSONObject();
                payload.put("title", title.getText().toString().trim());
                payload.put("event_type", VALUES[type.getSelectedItemPosition()]);
                payload.put("start_at", start.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME));
                payload.put("end_at", end.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME));
                payload.put("timezone", "Asia/Shanghai");
                payload.put("position", position.getText().toString().trim());
                payload.put("location_text", location.getText().toString().trim());
                payload.put("note", note.getText().toString().trim());
                if (rawInvitation != null && eventId == null) payload.put("raw_invitation", rawInvitation);
                JSONArray choices = new JSONArray();
                for (int i = 0; i < checks.length; i++) if (checks[i].isChecked()) choices.put(offsets[i]);
                payload.put("reminder_offsets_minutes", choices);
                actions.save(eventId, payload);
            } catch (Exception error) { title.setError("无法保存日程"); }
        });
        button("返回", false).setOnClickListener(v -> actions.back());
        scrollTo(0, 0);
    }

    private void renderDetail() {
        addHeading(event.optString("title", "日程详情"));
        int index = 0;
        for (int i = 0; i < VALUES.length; i++) if (VALUES[i].equals(event.optString("type"))) index = i;
        body.addView(text(TYPES[index] + " · " + displayDate(parseDate(event.optString("start_at"), ZonedDateTime.now(ZONE))) +
                " — " + displayDate(parseDate(event.optString("end_at"), ZonedDateTime.now(ZONE))), 15, false));
        for (String key : new String[]{"position", "location_text", "note"}) {
            String value = event.optString(key);
            if (!value.isEmpty() && !"null".equals(value)) {
                addLabel(key.equals("position") ? "应聘岗位" : key.equals("location_text") ? "地点" : "备注");
                body.addView(text(value, 16, false));
            }
        }
        button("编辑日程", true).setOnClickListener(v -> showForm(event));
        button("删除日程", false).setOnClickListener(v -> actions.delete(eventId));
        button("返回日历", false).setOnClickListener(v -> actions.back());
        scrollTo(0, 0);
    }
}
