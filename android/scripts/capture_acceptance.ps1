param(
    [string]$Serial = 'emulator-5554',
    [string]$Round = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$adb = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'
$apk = Join-Path $repoRoot 'android\app\build\outputs\apk\debug\app-debug.apk'
if (-not (Test-Path -LiteralPath $adb)) { throw '找不到 Android SDK 的 adb.exe' }
if (-not (Test-Path -LiteralPath $apk)) { throw '请先构建 Android debug APK' }

$deviceState = (& $adb -s $Serial get-state 2>$null)
if ($LASTEXITCODE -ne 0 -or $deviceState.Trim() -ne 'device') {
    throw "设备 $Serial 未连接或尚未开机"
}
if ($Serial.StartsWith('emulator-')) {
    & $adb -s $Serial shell wm size 1080x2400 | Out-Null
    & $adb -s $Serial shell wm density 420 | Out-Null
}

$chinaZone = [TimeZoneInfo]::FindSystemTimeZoneById('China Standard Time')
$day = [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $chinaZone).ToString('yyyy-MM-dd')
$destination = Join-Path $repoRoot "app\acceptance\$day"
if ($Round) {
    if ($Round -notmatch '^[a-z0-9-]+$') { throw 'Round 只允许小写字母、数字和连字符' }
    $destination = Join-Path $destination $Round
}
New-Item -ItemType Directory -Force -Path $destination | Out-Null

& $adb -s $Serial install -r $apk | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'APK 安装失败' }

$screens = @(
    @{ Mode = 'event'; Name = '01-native-event-top.png' },
    @{ Mode = 'event-reminders'; Name = '02-native-event-reminders.png' },
    @{ Mode = 'export'; Name = '03-native-export-page-1.png' },
    @{ Mode = 'export-page2'; Name = '04-native-export-page-2.png' },
    @{ Mode = 'export-options'; Name = '05-native-export-settings.png' }
)
if ($Round -in @('buttons', 'web-sync-v1-1', 'native-calendar-v1-2')) {
    $screens += @{ Mode = 'dashboard-home'; Name = '06-native-home-buttons.png' }
    $screens += @{ Mode = 'dashboard-calendar'; Name = '07-native-calendar-buttons.png' }
    $screens += @{ Mode = 'event-detail'; Name = '08-native-event-detail-buttons.png' }
}
if ($Round -in @('web-sync-v1-1', 'native-calendar-v1-2')) {
    $screens += @{ Mode = 'dashboard-next-day'; Name = '09-next-day-overnight-event.png' }
}
foreach ($screen in $screens) {
    & $adb -s $Serial shell am force-stop xyz.hunaochufang.awesomeinterview | Out-Null
    & $adb -s $Serial shell am start -n 'xyz.hunaochufang.awesomeinterview/.MainActivity' --es acceptance_screen $screen.Mode | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "无法打开验收页面：$($screen.Mode)" }
    Start-Sleep -Seconds 5
    & $adb -s $Serial shell screencap -p /sdcard/Download/awesome-acceptance.png | Out-Null
    $target = Join-Path $destination $screen.Name
    & $adb -s $Serial pull /sdcard/Download/awesome-acceptance.png $target | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "截图保存失败：$target" }
}
& $adb -s $Serial shell rm /sdcard/Download/awesome-acceptance.png | Out-Null

$manifest = [ordered]@{
    captured_at_china = [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $chinaZone).ToString('yyyy-MM-dd HH:mm:ss')
    app_version = '1.0.0-alpha3'
    device = $Serial
    apk = 'android/app/build/outputs/apk/debug/app-debug.apk'
    data = '本地合成示例；不包含真实用户数据'
    screens = @($screens | ForEach-Object { $_.Name })
}
$manifest | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $destination 'manifest.json') -Encoding UTF8
Write-Output $destination
