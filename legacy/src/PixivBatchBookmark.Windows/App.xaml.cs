using System.Threading;
using System.Windows;

namespace PixivBatchBookmark.Windows;

public partial class App : Application
{
    private Mutex? _instance;
    private bool _ownsMutex;
    private IntegratedHost? _host;
    protected override void OnStartup(StartupEventArgs e)
    {
        _instance = new Mutex(true, @"Local\PixivBatchBookmark.Windows.v1", out _ownsMutex);
        if (!_ownsMutex)
        {
            MessageBox.Show("程序已经运行，请使用已打开的窗口。", "Pixiv 批量收藏");
            Shutdown(); return;
        }
        base.OnStartup(e);
        var window = new MainWindow();
        MainWindow = window;
        if (e.Args.Contains("--integrated"))
        {
            _host = new IntegratedHost(window);
            window.EnableIntegratedMode(_host.ReturnToModern);
            RoutedEventHandler? loaded = null;
            loaded = (_, _) =>
            {
                window.Loaded -= loaded;
                window.Hide();
                _host.Ready();
            };
            window.Loaded += loaded;
            _host.Start();
        }
        window.Show();
    }
    protected override void OnExit(ExitEventArgs e)
    {
        _host?.Dispose();
        if (_ownsMutex) _instance?.ReleaseMutex();
        _instance?.Dispose(); base.OnExit(e);
    }
}
