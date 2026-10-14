using System.IO;
using System.Text;

namespace PixivBatchBookmark.Windows;

/// <summary>Fixed-word anonymous-pipe protocol; no account or task data crosses it.</summary>
internal sealed class IntegratedHost : IDisposable
{
    private readonly MainWindow _window;
    private readonly StreamReader _input;
    private readonly StreamWriter _output;

    public IntegratedHost(MainWindow window)
    {
        _window = window;
        _input = new StreamReader(Console.OpenStandardInput(), Encoding.UTF8);
        _output = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false))
        {
            AutoFlush = true, NewLine = "\n"
        };
    }

    public void Start() => _ = Task.Run(ReadCommandsAsync);
    public void Ready() => Send("READY");
    public void ReturnToModern() => Send("MODERN");

    private void Send(string token)
    {
        try { _output.WriteLine(token); }
        catch (IOException) { _window.RequestHostClose(); }
        catch (ObjectDisposedException) { }
    }

    private async Task ReadCommandsAsync()
    {
        try
        {
            while (await _input.ReadLineAsync() is { } command)
            {
                if (command == "EXIT") break;
                if (command != "LEGACY") continue;
                await _window.Dispatcher.InvokeAsync(() =>
                {
                    _window.Show();
                    if (_window.WindowState == System.Windows.WindowState.Minimized)
                        _window.WindowState = System.Windows.WindowState.Normal;
                    _window.Activate();
                    Send("SHOWN");
                });
            }
        }
        catch (IOException) { }
        catch (ObjectDisposedException) { return; }
        // EOF means the parent died: stop safely rather than orphaning a task.
        if (!_window.Dispatcher.HasShutdownStarted)
            await _window.Dispatcher.InvokeAsync(_window.RequestHostClose);
    }

    public void Dispose()
    {
        _output.Dispose();
        _input.Dispose();
    }
}
