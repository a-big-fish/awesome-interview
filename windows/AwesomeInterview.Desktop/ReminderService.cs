using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Windows.AppNotifications;
using Microsoft.Windows.AppNotifications.Builder;
using Windows.Data.Xml.Dom;
using Windows.UI.Notifications;

namespace AwesomeInterview.Desktop;

internal sealed class ReminderService
{
    private const string Group = "AwesomeInterview";
    public bool SchedulingAvailable { get; private set; } = true;
    public int ScheduledCount { get; private set; }

    public void Reconcile(JsonDocument snapshot)
    {
        CancelAll();
        var owner = snapshot.RootElement.GetProperty("user_id").GetString() ?? "";
        var now = DateTimeOffset.Now;
        foreach (var item in snapshot.RootElement.GetProperty("events").EnumerateArray())
        {
            if (!item.TryGetProperty("reminder_offsets_minutes", out var offsets) ||
                offsets.ValueKind != JsonValueKind.Array) continue;
            if (!DateTimeOffset.TryParse(item.GetProperty("start_at").GetString(), out var startsAt)) continue;
            var eventId = item.GetProperty("id").GetString() ?? "";
            foreach (var offsetElement in offsets.EnumerateArray())
            {
                if (!offsetElement.TryGetInt32(out var minutes) || minutes is not (10 or 60 or 1440)) continue;
                var dueAt = startsAt.AddMinutes(-minutes);
                if (dueAt <= now) continue;
                if (!SchedulingAvailable) continue;
                try
                {
                    var payload = new AppNotificationBuilder()
                        .AddArgument("event_id", eventId)
                        .AddText("Awesome Interview 日程提醒")
                        .AddText("有一项日程即将开始，点击查看")
                        .BuildNotification().Payload;
                    var xml = new XmlDocument();
                    xml.LoadXml(payload);
                    var scheduled = new ScheduledToastNotification(xml, dueAt)
                    {
                        Tag = StableTag(owner, eventId, minutes),
                        Group = Group
                    };
                    ToastNotificationManager.CreateToastNotifier().AddToSchedule(scheduled);
                    ScheduledCount++;
                }
                catch
                {
                    SchedulingAvailable = false;
                    CancelAll();
                }
            }
        }
    }

    public void CancelAll()
    {
        try
        {
            var notifier = ToastNotificationManager.CreateToastNotifier();
            foreach (var item in notifier.GetScheduledToastNotifications())
                if (item.Group == Group) notifier.RemoveFromSchedule(item);
        }
        catch
        {
            SchedulingAvailable = false;
        }
        ScheduledCount = 0;
    }

    private static string StableTag(string owner, string eventId, int minutes)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes($"{owner}:{eventId}:{minutes}"));
        return Convert.ToHexString(bytes)[..16];
    }
}
