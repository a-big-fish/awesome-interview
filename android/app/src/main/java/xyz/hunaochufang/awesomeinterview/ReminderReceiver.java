package xyz.hunaochufang.awesomeinterview;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;

public final class ReminderReceiver extends BroadcastReceiver {
    private static final String CHANNEL = "schedule_reminders";

    @Override public void onReceive(Context context, Intent intent) {
        if (Build.VERSION.SDK_INT >= 33 && context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) return;
        NotificationManager manager = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL, "日程提醒",
                NotificationManager.IMPORTANCE_HIGH));
        String eventId = intent.getStringExtra("event_id");
        Intent open = new Intent(context, MainActivity.class)
                .putExtra("event_id", eventId)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent action = PendingIntent.getActivity(context, eventId == null ? 0 : eventId.hashCode(),
                open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification notification = new Notification.Builder(context, CHANNEL)
                .setSmallIcon(android.R.drawable.ic_popup_reminder)
                .setContentTitle("Awesome Interview 日程提醒")
                .setContentText("有一项日程即将开始，点击查看")
                .setContentIntent(action).setAutoCancel(true).build();
        manager.notify((eventId == null ? "reminder" : eventId).hashCode(), notification);
    }
}
