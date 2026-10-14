"""Coordinate the original WPF app without transferring browser secrets."""

from pathlib import Path
import sys
from PySide6.QtCore import QObject, QProcess, QTimer, Signal


def legacy_command():
    if getattr(sys, 'frozen', False):
        directory = Path(sys.executable).resolve().parent / 'legacy'
    else:
        directory = Path(__file__).resolve().parents[1] / 'legacy' / 'dist' / 'win-x64'
    return [str(directory / 'PixivBatchBookmark.exe'), '--integrated']


class VersionSwitcher(QObject):
    availability_changed = Signal()
    failed = Signal(str)

    def __init__(self, window, command=None, startup_timeout_ms=15000, shutdown_timeout_ms=5000):
        super().__init__(window)
        self.window = window
        self.command = list(command) if command is not None else legacy_command()
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.readyReadStandardError.connect(self.process.readAllStandardError)
        self.process.errorOccurred.connect(self._process_error)
        self.process.finished.connect(self._finished)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(startup_timeout_ms)
        self.timer.timeout.connect(self._timeout)
        self.close_timer = QTimer(self)
        self.close_timer.setSingleShot(True)
        self.close_timer.setInterval(shutdown_timeout_ms)
        self.close_timer.timeout.connect(self._close_timeout)
        self.active_version = 'modern'
        self._pending = False
        self._closing = False
        self._failed_start = False
        self._buffer = b''
        self._activation_sent = False
        self._safe_to_kill = False
        self.shutdown_blocked = False

    @property
    def pending(self):
        return self._pending or self._closing

    @property
    def is_running(self):
        return self.process.state() != QProcess.ProcessState.NotRunning

    def switch_to_legacy(self):
        login = self.window.login_dialog
        if (self.pending or self.shutdown_blocked or self.active_version == 'legacy' or self.window.controller.running
                or (login is not None and login.isVisible())):
            return
        self._pending = True
        self._failed_start = False
        self.availability_changed.emit()
        self.timer.start()
        if self.is_running:
            self._activation_sent = True
            self.process.write(b'LEGACY\n')
        else:
            self._buffer = b''
            self._activation_sent = False
            self.process.setProgram(self.command[0])
            self.process.setArguments(self.command[1:])
            self.process.setWorkingDirectory(str(Path(self.command[0]).resolve().parent))
            self.process.start()

    def _read_output(self):
        self._buffer += bytes(self.process.readAllStandardOutput())
        if len(self._buffer) > 8192:
            self._buffer = b''
        while b'\n' in self._buffer:
            line, self._buffer = self._buffer.split(b'\n', 1)
            token = line.strip()
            if self._closing or self._failed_start:
                continue
            if token == b'READY' and self._pending:
                # The original WPF window remains hidden until this activation.
                self._activation_sent = True
                self.process.write(b'LEGACY\n')
            elif token == b'SHOWN' and self._pending:
                self.timer.stop()
                self._pending = False
                self.active_version = 'legacy'
                self.window.hide()
                self.availability_changed.emit()
            elif token == b'MODERN' and self.active_version == 'legacy':
                self.active_version = 'modern'
                self._activation_sent = False
                self._restore_modern()

    def _restore_modern(self):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()
        self.availability_changed.emit()

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.timer.stop()
            self._pending = False
            self._failed_start = True
            self._restore_modern()
            self.failed.emit('旧版启动失败。请完整解压合一版程序包；源码运行请先执行 build.ps1。')
            if self._closing:
                self._closing = False
                QTimer.singleShot(0, self.window.close)

    def _timeout(self):
        self._read_output()
        if not self._pending:
            return
        self._pending = False
        self._failed_start = True
        self.shutdown_blocked = self.is_running
        self.process.write(b'EXIT\n')
        if not self._activation_sent:
            # No LEGACY was sent: the WPF UI has never been made available.
            # kill(), unlike terminate(), also works for a hung WinExe/console.
            self.process.kill()
        else:
            # Activation may have reached WPF: never force-kill possible writes.
            self._safe_to_kill = False
            self.close_timer.start()
        self._restore_modern()
        self.failed.emit('旧版没有及时响应，已返回新版。请检查旧版程序和 WebView2 Runtime。')

    def _finished(self, code, status):
        self.timer.stop()
        self.close_timer.stop()
        self.shutdown_blocked = False
        was_pending = self._pending
        self._pending = False
        self.active_version = 'modern'
        if self._closing:
            self._closing = False
            QTimer.singleShot(0, self.window.close)
        elif self._failed_start:
            self._restore_modern()
        elif code != 0 or status == QProcess.ExitStatus.CrashExit or was_pending:
            self._restore_modern()
            self.failed.emit('旧版已异常退出，已返回新版。请检查旧版日志后再继续。')
        else:
            QTimer.singleShot(0, self.window.close)
        self.availability_changed.emit()

    def _close_timeout(self):
        if not self.is_running:
            return
        if self._safe_to_kill:
            self.process.kill()
            return
        self._closing = False
        self._pending = False
        self.shutdown_blocked = True
        self._restore_modern()
        self.failed.emit('旧版仍在退出或没有响应。为等待当前操作安全结束，暂时禁用收藏和版本切换；其他界面仍可使用。')

    def request_close(self):
        """False means the child is completing graceful shutdown."""
        if not self.is_running:
            return True
        if not self._closing:
            self._safe_to_kill = not self._activation_sent
            self._closing = True
            self.timer.stop()
            self.close_timer.start()
            self.availability_changed.emit()
            self.process.write(b'EXIT\n')
        return False
