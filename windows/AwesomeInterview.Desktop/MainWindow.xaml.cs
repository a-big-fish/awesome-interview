using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Threading;
using Microsoft.Web.WebView2.Core;
using Microsoft.Win32;
using Microsoft.Windows.AppNotifications;
using Microsoft.Windows.AppNotifications.Builder;
using Forms = System.Windows.Forms;

namespace AwesomeInterview.Desktop;

public partial class MainWindow : Window
{
    private static readonly string Origin = ReadServerOrigin();
    private static readonly string ServerAuthority = new Uri(Origin).Authority;
    private const string StartPath = "/my-schedule/experiences/plaza";
    private readonly SnapshotStore _store = new();
    private readonly ReminderService _reminders = new();
    private readonly HttpClient _http = new(new HttpClientHandler { AllowAutoRedirect = false })
    {
        Timeout = TimeSpan.FromSeconds(12)
    };
    private readonly Forms.NotifyIcon _tray;
    private readonly System.Drawing.Icon _appIcon;
    private readonly DispatcherTimer _fallbackTimer = new() { Interval = TimeSpan.FromSeconds(15) };
    private readonly DispatcherTimer _syncTimer = new() { Interval = TimeSpan.FromMinutes(5) };
    private readonly DispatcherTimer _writeSyncTimer = new() { Interval = TimeSpan.FromSeconds(2) };
    private readonly HashSet<string> _firedKeys;
    private DateTimeOffset _lastSyncAttempt = DateTimeOffset.MinValue;
    private bool _reallyClose;
    private bool _notificationRegistered;
    private bool _syncInProgress;

    private static string ReadServerOrigin()
    {
        var configured = Environment.GetEnvironmentVariable("AWESOME_INTERVIEW_SERVER_URL");
        if (Uri.TryCreate(configured, UriKind.Absolute, out var uri) &&
            uri.Scheme == Uri.UriSchemeHttps && uri.AbsolutePath == "/" &&
            string.IsNullOrEmpty(uri.Query) && string.IsNullOrEmpty(uri.Fragment))
            return uri.GetLeftPart(UriPartial.Authority);
        return "https://example.invalid";
    }

    public MainWindow()
    {
        InitializeComponent();
        _firedKeys = _store.ReadFiredKeys();
        using var iconStream = System.Windows.Application.GetResourceStream(
            new Uri("pack://application:,,,/Assets/app.ico"))!.Stream;
        _appIcon = new System.Drawing.Icon(iconStream);
        _tray = new Forms.NotifyIcon
        {
            Icon = _appIcon,
            Text = "Awesome Interview",
            Visible = true,
            ContextMenuStrip = new Forms.ContextMenuStrip()
        };
        _tray.ContextMenuStrip.Items.Add("打开", null, (_, _) => RestoreWindow());
        _tray.ContextMenuStrip.Items.Add("退出程序", null, (_, _) => ExitApplication());
        _tray.DoubleClick += (_, _) => RestoreWindow();
        Closing += OnClosing;
        _fallbackTimer.Tick += (_, _) => CheckFallbackReminders();
        _fallbackTimer.Start();
        _syncTimer.Tick += async (_, _) => await SyncAsync(false);
        _syncTimer.Start();
        _writeSyncTimer.Tick += async (_, _) =>
        {
            _writeSyncTimer.Stop();
            await SyncAsync(true);
        };
        Closed += (_, _) =>
        {
            _tray.Dispose();
            _appIcon.Dispose();
            _http.Dispose();
            if (_notificationRegistered) AppNotificationManager.Default.Unregister();
        };
        try
        {
            AppNotificationManager.Default.NotificationInvoked += OnNotificationInvoked;
            AppNotificationManager.Default.Register();
            _notificationRegistered = true;
        }
        catch
        {
            SyncLabel.Text = "系统通知注册失败；请检查 Windows 通知设置";
        }
        Loaded += async (_, _) => await InitializeBrowserAsync();
    }

    private async Task InitializeBrowserAsync()
    {
        try
        {
            var profile = Path.Combine(_store.DirectoryPath, "WebView2");
            var environment = await CoreWebView2Environment.CreateAsync(null, profile);
            await Browser.EnsureCoreWebView2Async(environment);
            Browser.CoreWebView2.Settings.AreDevToolsEnabled = false;
            Browser.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
            Browser.CoreWebView2.NavigationStarting += Browser_NavigationStarting;
            Browser.CoreWebView2.NavigationCompleted += Browser_NavigationCompleted;
            Browser.CoreWebView2.NewWindowRequested += Browser_NewWindowRequested;
            Browser.CoreWebView2.DownloadStarting += Browser_DownloadStarting;
            Browser.CoreWebView2.WebResourceResponseReceived += Browser_WebResourceResponseReceived;
            Browser.Source = new Uri(Origin + StartPath);
        }
        catch
        {
            ShowOffline();
        }
    }

    private void Browser_NavigationStarting(object? sender, CoreWebView2NavigationStartingEventArgs args)
    {
        if (!Uri.TryCreate(args.Uri, UriKind.Absolute, out var uri))
        {
            args.Cancel = true;
            return;
        }
        if (uri.Scheme == Uri.UriSchemeHttps && uri.Authority == ServerAuthority) return;
        args.Cancel = true;
        if (uri.Scheme is "https" or "http") OpenExternal(uri.AbsoluteUri);
    }

    private void Browser_NewWindowRequested(object? sender, CoreWebView2NewWindowRequestedEventArgs args)
    {
        args.Handled = true;
        if (!Uri.TryCreate(args.Uri, UriKind.Absolute, out var uri)) return;
        if (uri.Scheme == Uri.UriSchemeHttps && uri.Authority == ServerAuthority)
            Browser.Source = uri;
        else if (uri.Scheme is "https" or "http") OpenExternal(uri.AbsoluteUri);
    }

    private static void OpenExternal(string url)
    {
        Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
    }

    private async void Browser_NavigationCompleted(object? sender, CoreWebView2NavigationCompletedEventArgs args)
    {
        if (!args.IsSuccess || args.HttpStatusCode >= 500)
        {
            ShowOffline();
            return;
        }
        var path = Browser.Source?.AbsolutePath ?? "";
        if (path.StartsWith("/auth/login", StringComparison.Ordinal))
        {
            if (_store.OwnerId() is not null) await ClearLocalAsync();
            HideOffline();
            return;
        }
        if (!path.StartsWith("/my-schedule", StringComparison.Ordinal)) return;
        HideOffline();
        await Browser.ExecuteScriptAsync(
            "(function(){let h=document.querySelector('.page-header');if(h)h.style.display='none'})()");
        await SyncAsync(false);
    }

    private void Browser_DownloadStarting(object? sender, CoreWebView2DownloadStartingEventArgs args)
    {
        var save = new Microsoft.Win32.SaveFileDialog
        {
            FileName = Path.GetFileName(args.ResultFilePath),
            Filter = "所有文件|*.*"
        };
        if (save.ShowDialog(this) == true) args.ResultFilePath = save.FileName;
        else args.Cancel = true;
    }

    private void Browser_WebResourceResponseReceived(object? sender,
        CoreWebView2WebResourceResponseReceivedEventArgs args)
    {
        if (args.Request.Method is not ("POST" or "PUT" or "PATCH" or "DELETE") ||
            !Uri.TryCreate(args.Request.Uri, UriKind.Absolute, out var uri) ||
            uri.Scheme != Uri.UriSchemeHttps || uri.Authority != ServerAuthority ||
            !uri.AbsolutePath.StartsWith("/my-schedule", StringComparison.Ordinal) ||
            args.Response.StatusCode >= 400) return;
        Dispatcher.BeginInvoke(() =>
        {
            _writeSyncTimer.Stop();
            _writeSyncTimer.Start();
        });
    }

    private async Task SyncAsync(bool force)
    {
        if (Browser.CoreWebView2 is null || _syncInProgress) return;
        if (!force && DateTimeOffset.Now - _lastSyncAttempt < TimeSpan.FromSeconds(30)) return;
        _lastSyncAttempt = DateTimeOffset.Now;
        _syncInProgress = true;
        try
        {
            var cookies = await Browser.CoreWebView2.CookieManager.GetCookiesAsync(Origin);
            if (cookies.Count == 0) return;
            using var request = new HttpRequestMessage(HttpMethod.Get, Origin + "/api/mobile/v1/snapshot");
            request.Headers.TryAddWithoutValidation("Cookie", string.Join("; ", cookies.Select(c => $"{c.Name}={c.Value}")));
            request.Headers.Accept.ParseAdd("application/json");
            using var response = await _http.SendAsync(request);
            if (response.StatusCode != HttpStatusCode.OK ||
                response.Content.Headers.ContentType?.MediaType != "application/json") return;
            using var document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
            var owner = document.RootElement.GetProperty("user_id").GetString();
            var previous = _store.OwnerId();
            if (previous is not null && previous != owner)
            {
                _reminders.CancelAll();
                _store.Clear();
                _firedKeys.Clear();
            }
            _store.Save(document);
            _reminders.Reconcile(document);
            SyncLabel.Text = "已同步 " + document.RootElement.GetProperty("server_time").GetString() +
                (_reminders.SchedulingAvailable ? $" · 已登记 {_reminders.ScheduledCount} 项提醒" :
                    " · 托盘运行时提醒");
        }
        catch
        {
            SyncLabel.Text = "同步失败，保留上次缓存";
        }
        finally
        {
            _syncInProgress = false;
        }
    }

    private async Task ClearLocalAsync()
    {
        _reminders.CancelAll();
        _store.Clear();
        _firedKeys.Clear();
        SyncLabel.Text = "已退出，缓存已清除";
        if (Browser.CoreWebView2 is not null)
        {
            Browser.CoreWebView2.CookieManager.DeleteAllCookies();
            await Browser.CoreWebView2.Profile.ClearBrowsingDataAsync();
        }
    }

    private void ShowOffline()
    {
        Browser.Visibility = Visibility.Collapsed;
        OfflinePanel.Visibility = Visibility.Visible;
        using var document = _store.Read();
        if (document is null)
        {
            OfflineSubtitle.Text = "服务器暂不可用，本机还没有成功同步的内容。";
            OfflineContent.Text = "连接服务器并登录后，才能建立离线只读缓存。";
            return;
        }
        var root = document.RootElement;
        OfflineSubtitle.Text = "最近同步：" + root.GetProperty("server_time").GetString() + " · 内容可能已过期";
        var text = new StringBuilder("日程\n\n");
        foreach (var item in root.GetProperty("events").EnumerateArray())
        {
            text.Append("• ").Append(Value(item, "title")).Append("\n  ")
                .Append(Value(item, "start_at")).Append('\n');
            if (!string.IsNullOrWhiteSpace(Value(item, "location_text")))
                text.Append("  地点：").Append(Value(item, "location_text")).Append('\n');
            if (!string.IsNullOrWhiteSpace(Value(item, "note")))
                text.Append("  备注：").Append(Value(item, "note")).Append('\n');
        }
        text.Append("\n我的面经\n\n");
        foreach (var item in root.GetProperty("experiences").EnumerateArray())
        {
            text.Append("• ").Append(Value(item, "title")).Append('\n');
            if (!string.IsNullOrWhiteSpace(Value(item, "company")))
                text.Append("  公司：").Append(Value(item, "company")).Append('\n');
            if (!string.IsNullOrWhiteSpace(Value(item, "feeling")))
                text.Append("  面试感受：").Append(Value(item, "feeling")).Append('\n');
            foreach (var question in item.GetProperty("questions").EnumerateArray())
            {
                text.Append("  - ").Append(Value(question, "question_text")).Append('\n');
                foreach (var (key, label) in new[] {
                    ("on_site_answer", "现场回答"), ("review_answer", "复盘答案"),
                    ("interviewer_answer", "面试官回答") })
                    if (!string.IsNullOrWhiteSpace(Value(question, key)))
                        text.Append("    ").Append(label).Append("：")
                            .Append(Value(question, key)).Append('\n');
            }
        }
        OfflineContent.Text = text.ToString();
    }

    private static string Value(JsonElement item, string key) =>
        item.TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? "" : "";

    private void CheckFallbackReminders()
    {
        if (_reminders.SchedulingAvailable) return;
        using var document = _store.Read();
        if (document is null) return;
        var owner = Value(document.RootElement, "user_id");
        var now = DateTimeOffset.Now;
        foreach (var item in document.RootElement.GetProperty("events").EnumerateArray())
        {
            if (!DateTimeOffset.TryParse(Value(item, "start_at"), out var startsAt) ||
                !item.TryGetProperty("reminder_offsets_minutes", out var offsets) ||
                offsets.ValueKind != JsonValueKind.Array) continue;
            foreach (var element in offsets.EnumerateArray())
            {
                if (!element.TryGetInt32(out var minutes) || minutes is not (10 or 60 or 1440)) continue;
                var dueAt = startsAt.AddMinutes(-minutes);
                if (now < dueAt || now - dueAt > TimeSpan.FromMinutes(1)) continue;
                var key = $"{owner}:{Value(item, "id")}:{minutes}:{startsAt:O}";
                if (!_firedKeys.Add(key)) continue;
                try { _store.SaveFiredKeys(_firedKeys); } catch { /* Keep the reminder visible now. */ }
                try
                {
                    if (!_notificationRegistered) throw new InvalidOperationException();
                    var notice = new AppNotificationBuilder()
                        .AddArgument("event_id", Value(item, "id"))
                        .AddText("Awesome Interview 日程提醒")
                        .AddText("有一项日程即将开始，点击查看")
                        .BuildNotification();
                    AppNotificationManager.Default.Show(notice);
                }
                catch
                {
                    _tray.ShowBalloonTip(5000, "Awesome Interview", "有一项日程即将开始",
                        Forms.ToolTipIcon.Info);
                }
            }
        }
    }

    private void HideOffline()
    {
        OfflinePanel.Visibility = Visibility.Collapsed;
        Browser.Visibility = Visibility.Visible;
    }

    private void OnNotificationInvoked(AppNotificationManager sender, AppNotificationActivatedEventArgs args)
    {
        Dispatcher.Invoke(() =>
        {
            RestoreWindow();
            var argument = args.Argument.Split('&').FirstOrDefault(x => x.StartsWith("event_id="));
            if (argument is not null)
            {
                var id = Uri.UnescapeDataString(argument["event_id=".Length..]);
                if (Guid.TryParse(id, out _)) Browser.Source = new Uri(Origin + "/my-schedule/events/" + id);
            }
        });
    }

    private void RestoreWindow()
    {
        Show();
        WindowState = WindowState.Normal;
        Activate();
    }

    private void OnClosing(object? sender, CancelEventArgs args)
    {
        if (_reallyClose) return;
        args.Cancel = true;
        Hide();
        _tray.ShowBalloonTip(2000, "Awesome Interview", "已在托盘保持运行和日程提醒", Forms.ToolTipIcon.Info);
    }

    private void ExitApplication()
    {
        _reallyClose = true;
        Close();
        System.Windows.Application.Current.Shutdown();
    }

    private async void Navigate_Click(object sender, RoutedEventArgs args)
    {
        if (sender is not FrameworkElement { Tag: string path }) return;
        if (Browser.CoreWebView2 is not null &&
            path is ("/my-schedule" or "/my-schedule/experiences" or "/my-schedule/experiences/plaza"))
        {
            try
            {
                var script = "Boolean(window.awesomeInterviewNavigate && " +
                             "window.awesomeInterviewNavigate(" + JsonSerializer.Serialize(path) + "))";
                if (await Browser.ExecuteScriptAsync(script) == "true") return;
            }
            catch { /* A full navigation below handles pages without the cache script. */ }
        }
        Browser.Source = new Uri(Origin + path);
    }

    private async void Sync_Click(object sender, RoutedEventArgs args) => await SyncAsync(true);

    private async void Logout_Click(object sender, RoutedEventArgs args)
    {
        if (Browser.CoreWebView2 is null) return;
        await Browser.ExecuteScriptAsync(
            "(function(){let f=document.querySelector('.nav-logout-form');if(f)f.submit()})()");
    }

    private void Reconnect_Click(object sender, RoutedEventArgs args) =>
        Browser.Source = new Uri(Origin + StartPath);
}
