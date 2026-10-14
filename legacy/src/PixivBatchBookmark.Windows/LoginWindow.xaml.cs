using System.ComponentModel;
using System.IO;
using System.Net;
using System.Text.Json;
using System.Windows;
using Microsoft.Web.WebView2.Core;
using PixivBatchBookmark.Core;

namespace PixivBatchBookmark.Windows;

public record LoginResult(LoginSession Session, IReadOnlyList<Cookie> Cookies, string UserAgent);

public partial class LoginWindow : Window
{
    public LoginResult? Result { get; private set; }
    private readonly CancellationTokenSource _closed = new();
    private bool _checking;
    public LoginWindow() => InitializeComponent();

    private async void Window_Loaded(object sender, RoutedEventArgs e)
    {
        try
        {
            var folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PixivBatchBookmark", "WebView2");
            var environment = await CoreWebView2Environment.CreateAsync(null, folder);
            if (_closed.IsCancellationRequested) return;
            await Browser.EnsureCoreWebView2Async(environment);
            if (_closed.IsCancellationRequested) return;
            Browser.CoreWebView2.Settings.AreDevToolsEnabled = false;
            Browser.CoreWebView2.Settings.IsPasswordAutosaveEnabled = false;
            Browser.CoreWebView2.Settings.IsGeneralAutofillEnabled = false;
            Browser.CoreWebView2.NewWindowRequested += (_, args) =>
            {
                args.Handled = true;
                if (Uri.TryCreate(args.Uri, UriKind.Absolute, out var uri) && uri.Scheme == "https") Browser.CoreWebView2.Navigate(args.Uri);
            };
            Browser.Source = new Uri("https://www.pixiv.net/");
            ConfirmButton.IsEnabled = GoLoginButton.IsEnabled = GoHomeButton.IsEnabled = true;
            Status.Text = "已有登录可直接检查；需要登录或切换账号时，请在官方页面操作。";
        }
        catch (Exception) { if (!_closed.IsCancellationRequested) Status.Text = "无法初始化内置浏览器。请安装 Microsoft Edge WebView2 Runtime，关闭窗口后重试。"; }
    }
    private void GoLogin_Click(object sender, RoutedEventArgs e) => Browser.CoreWebView2.Navigate("https://accounts.pixiv.net/login?return_to=https%3A%2F%2Fwww.pixiv.net%2F");
    private void GoHome_Click(object sender, RoutedEventArgs e) => Browser.CoreWebView2.Navigate("https://www.pixiv.net/");

    private async void Confirm_Click(object sender, RoutedEventArgs e)
    {
        if (_checking || Browser.CoreWebView2 is null) return;
        _checking = true; ConfirmButton.IsEnabled = GoLoginButton.IsEnabled = GoHomeButton.IsEnabled = false;
        try
        {
            Status.Text = "检查官方页面中的登录身份和收藏安全令牌……";
            // Always load a fresh first-party page after login. Never accept identity
            // data or tokens from an OAuth provider, a redirect URL, or a foreign page.
            Browser.CoreWebView2.Navigate("https://www.pixiv.net/");
            LoginSession? session = null;
            for (var attempt = 0; attempt < 40; attempt++)
            {
                await Task.Delay(500, _closed.Token);
                if (!Uri.TryCreate(Browser.Source?.AbsoluteUri, UriKind.Absolute, out var uri) ||
                    uri.Scheme != "https" || !(uri.Host == "www.pixiv.net" || uri.Host == "pixiv.net")) continue;
                // Read both supported first-party page formats; the current homepage
                // stores identity and token in __NEXT_DATA__ rather than a meta tag.
                var encoded = await Browser.ExecuteScriptAsync("Array.from(document.querySelectorAll('meta[name=\"global-data\"], script#__NEXT_DATA__')).map(node => node.outerHTML).join('')");
                try { session = SessionParser.Parse(JsonSerializer.Deserialize<string>(encoded) ?? ""); break; }
                catch (PixivException) { /* The navigation may not have finished loading metadata. */ }
            }
            if (session is null) throw new PixivException("尚未检测到有效登录。请完成账号登录/验证码，返回 Pixiv 首页后重试。若网站结构变化，需要更新程序。");
            var snapshot = await Browser.CoreWebView2.CookieManager.GetCookiesAsync("https://www.pixiv.net/");
            if (!snapshot.Any(cookie => cookie.Name == "PHPSESSID" && !string.IsNullOrEmpty(cookie.Value))) throw new PixivException("登录 Cookie 尚未就绪，请重新登录后再检查。");
            var cookies = snapshot.Select(cookie => new Cookie(cookie.Name, cookie.Value, cookie.Path, cookie.Domain)
            {
                Secure = cookie.IsSecure, HttpOnly = cookie.IsHttpOnly,
                Expires = cookie.IsSession ? DateTime.MinValue : cookie.Expires
            }).ToArray();
            var agent = JsonSerializer.Deserialize<string>(await Browser.ExecuteScriptAsync("navigator.userAgent")) ?? "Mozilla/5.0";
            _closed.Token.ThrowIfCancellationRequested();
            Result = new(session, cookies, agent); DialogResult = true;
        }
        catch (OperationCanceledException) { }
        catch (Exception ex) { Status.Text = ex is PixivException ? ex.Message : "登录检查失败，请检查 Windows 系统代理与网络，完成网页验证后重试。"; }
        finally
        {
            _checking = false;
            if (!_closed.IsCancellationRequested) ConfirmButton.IsEnabled = GoLoginButton.IsEnabled = GoHomeButton.IsEnabled = true;
        }
    }
    private void Window_Closing(object? sender, CancelEventArgs e)
    {
        _closed.Cancel(); Browser.Dispose();
    }
}
