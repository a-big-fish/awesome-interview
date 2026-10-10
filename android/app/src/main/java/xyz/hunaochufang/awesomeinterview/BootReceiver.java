package xyz.hunaochufang.awesomeinterview;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class BootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if (!Intent.ACTION_BOOT_COMPLETED.equals(action)
                && !Intent.ACTION_TIMEZONE_CHANGED.equals(action)
                && !Intent.ACTION_TIME_CHANGED.equals(action)
                && !"android.app.action.SCHEDULE_EXACT_ALARM_PERMISSION_STATE_CHANGED".equals(action)) return;
        try {
            ReminderScheduler.reschedule(context, OfflineStore.load(context));
        } catch (Exception ignored) {
            // No signed-in user's snapshot exists on this device.
        }
    }
}
