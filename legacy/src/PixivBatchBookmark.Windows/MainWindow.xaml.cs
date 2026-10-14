using System.Collections.ObjectModel;
using System.ComponentModel;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Windows;
using System.Windows.Media.Imaging;
using PixivBatchBookmark.Core;

namespace PixivBatchBookmark.Windows;

public partial class MainWindow : Window
{
    private readonly ObservableCollection<string> _rows = [];
    private readonly string _logPath;
    private IReadOnlyList<string> _ids = [];
    private HttpClient? _http;
    private LoginSession? _session;
    private CancellationTokenSource? _stop;
    private bool _busy;
    private bool _alternateWallpaper;
    private Action? _returnToModern;
    private bool _closeWhenIdle;

    public MainWindow()
    {
        InitializeComponent();
        IdList.ItemsSource = _rows;
        _logPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PixivBatchBookmark", "Logs", $"{DateTime.Now:yyyy-MM-dd}.log");
        Log("准备就绪。先登录 Pixiv，再粘贴作品 ID 或链接并解析。");
    }

    public void EnableIntegratedMode(Action returnToModern)
    {
        _returnToModern = returnToModern;
        Title += " · 旧版";
        ModeSwitchButton.Visibility = Visibility.Visible;
        ModeSwitchButton.IsEnabled = !_busy;
    }

    private void ModeSwitch_Click(object sender, RoutedEventArgs e)
    {
        if (_busy || _closeWhenIdle || _returnToModern is null || OwnedWindows.Count > 0) return;
        Hide();
        _returnToModern();
    }

    public void RequestHostClose()
    {
        _closeWhenIdle = true;
        if (_busy)
        {
            _stop?.Cancel();
            StopButton.IsEnabled = ModeSwitchButton.IsEnabled = false;
            Log("合一版正在退出，将在当前操作与必要恢复完成后关闭。");
        }
        else
        {
            // A host may exit while the official login dialog is open.
            foreach (Window owned in OwnedWindows.Cast<Window>().ToArray()) owned.Close();
            Close();
        }
    }

    private void Wallpaper_Click(object sender, RoutedEventArgs e)
    {
        // Change only visibility and layering; inputs and running tasks keep their state.
        var wallpaperOnly = InterfacePanel.Visibility == Visibility.Visible;
        InterfacePanel.Visibility = WallpaperShade.Visibility = wallpaperOnly ? Visibility.Collapsed : Visibility.Visible;
        WallpaperImage.HorizontalAlignment = wallpaperOnly ? HorizontalAlignment.Center : HorizontalAlignment.Right;
        System.Windows.Controls.Panel.SetZIndex(WallpaperImage, wallpaperOnly ? 3 : 0);
        WallpaperButton.Content = wallpaperOnly ? "再见兽娘麻麻⊙﹏⊙" : "看看兽娘麻麻˃ 𖥦 ˂ ";
    }

    private void NextWallpaper_Click(object sender, RoutedEventArgs e)
    {
        // Replace only the image source so the current viewing mode and task state stay intact.
        _alternateWallpaper = !_alternateWallpaper;
        var fileName = _alternateWallpaper ? "Wallpaper2.jpg" : "Wallpaper.png";
        WallpaperImage.Source = new BitmapImage(new Uri($"pack://application:,,,/PixivBatchBookmark;component/Assets/{fileName}", UriKind.Absolute));
        NextWallpaperButton.Content = _alternateWallpaper ? "切换壁纸（2/2）" : "切换壁纸（1/2）";
    }

    private void Parse_Click(object sender, RoutedEventArgs e) => ParseInput();
    private void Clear_Click(object sender, RoutedEventArgs e)
    {
        InputBox.Clear(); _ids = []; _rows.Clear();
        ParseStatus.Text = "支持插画 / 漫画；自动去重";
        Summary.Text = "等待输入作品"; TaskProgress.Value = 0;
    }
    private void ParseInput()
    {
        var parsed = IdParser.Parse(InputBox.Text);
        _ids = parsed.Ids; _rows.Clear();
        foreach (var id in _ids) _rows.Add($"待处理  ·  {id}");
        ParseStatus.Text = $"{_ids.Count} 个 ID · 去重 {parsed.DuplicateCount} · 忽略 {parsed.IgnoredLines.Count} 行";
        Summary.Text = $"已解析 {_ids.Count} 个作品，开始前请检查右侧 ID 列表";
        Log($"解析得到 {_ids.Count} 个作品，去除 {parsed.DuplicateCount} 个重复，忽略 {parsed.IgnoredLines.Count} 行。");
        if (parsed.IgnoredLines.Count > 0) Log("未识别行未加入任务。标题中的数字、作者链接和小说链接不会自动当作插画 ID。");
    }

    private void Login_Click(object sender, RoutedEventArgs e)
    {
        var window = new LoginWindow { Owner = this };
        if (window.ShowDialog() != true || window.Result is null) return;
        var result = window.Result;
        _http?.Dispose();
        var cookies = new CookieContainer();
        foreach (var cookie in result.Cookies) cookies.Add(cookie);
        var handler = new HttpClientHandler { CookieContainer = cookies, AllowAutoRedirect = false, UseProxy = true, AutomaticDecompression = DecompressionMethods.All };
        _http = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(30) };
        _http.DefaultRequestHeaders.UserAgent.ParseAdd(result.UserAgent);
        _http.DefaultRequestHeaders.AcceptLanguage.ParseAdd("zh-CN,zh;q=0.9,en;q=0.8");
        _session = result.Session;
        LoginStatus.Text = $"● 已登录：{_session.UserName}（ID {_session.UserId}）";
        SetBusy(false); Log("官方网页登录身份和收藏安全令牌检查通过。");
    }

    private async void CheckLogin_Click(object sender, RoutedEventArgs e)
    {
        SetBusy(true);
        try { await VerifySessionAsync(CancellationToken.None); Log("登录检查通过，可以开始任务。"); }
        catch (Exception ex) { InvalidateSession(); Log(UserMessage(ex)); }
        finally { SetBusy(false); }
    }

    private async Task VerifySessionAsync(CancellationToken cancellationToken)
    {
        if (_http is null || _session is null) throw new PixivException("请先完成 Pixiv 登录");
        using var request = new HttpRequestMessage(HttpMethod.Get, "https://www.pixiv.net/");
        request.Headers.CacheControl = new() { NoCache = true, NoStore = true };
        using var response = await _http.SendAsync(request, cancellationToken);
        if (!response.IsSuccessStatusCode) throw new PixivException($"登录检查未通过（{(int)response.StatusCode}），请重新登录或完成网页验证");
        var refreshed = SessionParser.Parse(await response.Content.ReadAsStringAsync(cancellationToken));
        if (refreshed.UserId != _session.UserId) throw new PixivException("登录账号发生变化，请重新确认登录后再开始任务");
        _session = refreshed;
        LoginStatus.Text = $"● 已登录：{refreshed.UserName}（ID {refreshed.UserId}）";
    }

    private async void Bookmark_Click(object sender, RoutedEventArgs e) => await RunBatchAsync(BatchAction.Bookmark);
    private async void Remove_Click(object sender, RoutedEventArgs e) => await RunBatchAsync(BatchAction.Remove);

    private async Task RunBatchAsync(BatchAction action)
    {
        if (_busy || _http is null || _session is null) return;
        ParseInput();
        if (_ids.Count == 0) { Log("没有有效的作品 ID，任务未开始。"); return; }
        var mode = PrivateMode.IsChecked == true ? BookmarkMode.Private : BookmarkMode.Public;
        var ids = _ids.ToArray(); // Fix the batch input before the first request.
        _stop = new CancellationTokenSource(); SetBusy(true); StopButton.IsEnabled = true;
        var success = 0; var skipped = 0; var failed = 0; var processed = 0;
        var ending = "完成";
        TaskProgress.Maximum = ids.Length; TaskProgress.Value = 0;
        try
        {
            Log("开始前检查登录与收藏安全令牌……");
            try { await VerifySessionAsync(_stop.Token); }
            catch (OperationCanceledException) { throw; }
            catch { InvalidateSession(); throw; }
            var service = new BookmarkService(new PixivHttpClient(_http!, _session!));
            Log(action == BatchAction.Remove ? $"开始批量取消收藏，共 {ids.Length} 项。" : $"开始{BookmarkService.ModeName(mode)}收藏，共 {ids.Length} 项。");
            for (var i = 0; i < ids.Length; i++)
            {
                _stop.Token.ThrowIfCancellationRequested();
                var id = ids[i]; _rows[i] = $"处理中  ·  {id}";
                IdList.ScrollIntoView(_rows[i]);
                Log($"[{i + 1}/{ids.Length}] 检查 {id}");
                var result = await service.ProcessAsync(id, action, mode, _stop.Token, message => Log($"{id}  {message}"));
                var label = result.Status switch { ItemStatus.Success => "成功", ItemStatus.Skipped => "跳过", _ => "失败" };
                _rows[i] = $"{label}  ·  {id}"; Log($"{id}  {label}：{result.Message}");
                if (result.Status == ItemStatus.Success) success++;
                else if (result.Status == ItemStatus.Skipped) skipped++; else failed++;
                processed++; TaskProgress.Value = processed;
                Summary.Text = $"已处理 {processed}/{ids.Length} · 成功 {success} · 跳过 {skipped} · 失败 {failed}";
                if (result.StopBatch) { ending = "已停止，请查看日志"; break; }
                if (i < ids.Length - 1) await Task.Delay(1500, _stop.Token);
            }
        }
        catch (OperationCanceledException) { ending = "用户已停止"; Log("任务停止，当前作品已处理结束，其余作品未提交。"); }
        catch (Exception ex) { ending = "未完成，请查看日志"; Log(UserMessage(ex)); }
        finally
        {
            Summary.Text = $"{ending} · 成功 {success} · 跳过 {skipped} · 失败 {failed} · 未处理 {ids.Length - processed}";
            Log(Summary.Text); _stop.Dispose(); _stop = null; SetBusy(false);
        }
    }

    private void Stop_Click(object sender, RoutedEventArgs e)
    {
        _stop?.Cancel(); StopButton.IsEnabled = false;
        Log("已请求停止，将在当前作品处理与必要恢复完成后结束。");
    }
    private void SetBusy(bool busy)
    {
        _busy = busy; InputBox.IsReadOnly = busy || _closeWhenIdle;
        var enabled = !busy && !_closeWhenIdle;
        LoginButton.IsEnabled = ParseButton.IsEnabled = ClearButton.IsEnabled = PublicMode.IsEnabled = PrivateMode.IsEnabled = enabled;
        CheckLoginButton.IsEnabled = BookmarkButton.IsEnabled = RemoveButton.IsEnabled = enabled && _session is not null;
        ModeSwitchButton.IsEnabled = enabled;
        StopButton.IsEnabled = busy && _stop is not null;
        if (!busy && _closeWhenIdle) Dispatcher.BeginInvoke(new Action(RequestHostClose));
    }
    private void InvalidateSession() { _session = null; LoginStatus.Text = "● 登录需要重新检查"; }
    private static string UserMessage(Exception ex) => ex is PixivException ? ex.Message : ex is TaskCanceledException ? "请求超时，请检查 Windows 系统代理和网络后重试。" : "连接失败，请检查网络、网页登录和 WebView2 Runtime。";
    private void Log(string message)
    {
        var line = $"[{DateTime.Now:HH:mm:ss}] {message}{Environment.NewLine}";
        if (LogBox.LineCount > 2500) LogBox.Text = string.Join(Environment.NewLine, LogBox.Text.Split(Environment.NewLine).TakeLast(1500)) + Environment.NewLine;
        LogBox.AppendText(line); LogBox.ScrollToEnd();
        try { Directory.CreateDirectory(Path.GetDirectoryName(_logPath)!); File.AppendAllText(_logPath, line, System.Text.Encoding.UTF8); }
        catch (IOException) { LogFileStatus.Text = "文件日志写入失败，窗口日志仍可复制"; }
        catch (UnauthorizedAccessException) { LogFileStatus.Text = "文件日志写入失败，窗口日志仍可复制"; }
    }
    private void Window_Closing(object? sender, CancelEventArgs e)
    {
        if (_busy)
        {
            e.Cancel = true; _stop?.Cancel(); StopButton.IsEnabled = false;
            Log("正在完成当前操作，请待任务停止后再关闭窗口。"); return;
        }
        _http?.Dispose();
    }
}
