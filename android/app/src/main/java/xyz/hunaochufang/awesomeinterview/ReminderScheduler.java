package xyz.hunaochufang.awesomeinterview;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.time.OffsetDateTime;

final class ReminderScheduler {
    private static final String IDS = "alarm_ids";

    private ReminderScheduler() { }

    static void cancelAll(Context context) {
        SharedPreferences prefs = OfflineStore.prefs(context);
        AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        String encoded = prefs.getString(IDS, "[]");
        try {
            JSONArray ids = new JSONArray(encoded);
            for (int i = 0; i < ids.length(); i++) {
                int id = ids.getInt(i);
                PendingIntent pending = pending(context, id, "", "", PendingIntent.FLAG_NO_CREATE);
                if (pending != null) {
                    alarms.cancel(pending);
                    pending.cancel();
                }
            }
        } catch (Exception ignored) {
            // The next successful snapshot rewrites this local index.
        }
        prefs.edit().remove(IDS).apply();
    }

    static int reschedule(Context context, JSONObject snapshot) throws Exception {
        cancelAll(context);
        AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        JSONArray ids = new JSONArray();
        JSONArray events = snapshot.getJSONArray("events");
        String owner = snapshot.getString("user_id");
        long now = System.currentTimeMillis();
        int count = 0;
        for (int i = 0; i < events.length(); i++) {
            JSONObject event = events.getJSONObject(i);
            JSONArray offsets = event.optJSONArray("reminder_offsets_minutes");
            if (offsets == null) continue;
            long startsAt = OffsetDateTime.parse(event.getString("start_at")).toInstant().toEpochMilli();
            for (int j = 0; j < offsets.length(); j++) {
                int offset = offsets.getInt(j);
                if (offset != 10 && offset != 60 && offset != 1440) continue;
                long triggerAt = startsAt - offset * 60_000L;
                if (triggerAt <= now) continue;
                int id = (owner + ":" + event.getString("id") + ":" + offset).hashCode();
                PendingIntent pending = pending(context, id, event.getString("id"), event.optString("title"),
                        PendingIntent.FLAG_UPDATE_CURRENT);
                if (Build.VERSION.SDK_INT >= 31 && alarms.canScheduleExactAlarms()) {
                    alarms.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAt, pending);
                } else {
                    alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAt, pending);
                }
                ids.put(id);
                count++;
            }
        }
        OfflineStore.prefs(context).edit().putString(IDS, ids.toString()).apply();
        return count;
    }

    private static PendingIntent pending(Context context, int id, String eventId, String title, int flag) {
        Intent intent = new Intent(context, ReminderReceiver.class)
                .putExtra("event_id", eventId).putExtra("title", title);
        return PendingIntent.getBroadcast(context, id, intent, flag | PendingIntent.FLAG_IMMUTABLE);
    }
}
