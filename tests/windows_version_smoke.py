"""Real WPF/Qt pipe + button + package checks, without connecting to Pixiv."""

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if sys.platform != 'win32':
    raise SystemExit('Run this test on Windows x64 after build.ps1.')

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from ui.window import MainWindow


def wait_until(predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert predicate(), 'Timed out waiting for real WPF/Qt state'


def close_native_window(pid):
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    found = []
    def visit(hwnd, _):
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        return True
    callback = callback_type(visit)
    user32.EnumWindows(callback, 0)
    return bool(found)


app = QApplication([])
app.setQuitOnLastWindowClosed(False)
with tempfile.TemporaryDirectory(prefix='unified smoke ', ignore_cleanup_errors=True) as data:
    os.environ['LOCALAPPDATA'] = data
    window = MainWindow(offline=True)
    window.version_switcher.failed.connect(lambda message: errors.append(message))
    # Remove the modal warning slot so failures can be reported by the test.
    window.version_switcher.failed.disconnect(window._version_error)
    errors = []
    closed = []
    window.closed.connect(lambda: closed.append(True))
    window.show()
    window.input_edit.setPlainText('97003966\n103816477')
    window.parse_input()
    window.toggle_wallpaper()
    switcher = window.version_switcher
    try:
        pid = None
        for _ in range(2):
            window.version_button.click()
            wait_until(lambda: switcher.active_version == 'legacy' or bool(errors))
            assert not errors, errors
            current_pid = switcher.process.processId()
            assert pid is None or pid == current_pid, 'Legacy process was not reused'
            pid = current_pid
            assert not window.isVisible()
            subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                str(ROOT / 'tests/click_legacy_return.ps1'), '-LegacyProcessId', str(pid)],
                check=True, timeout=20)
            wait_until(window.isVisible)
            assert window.ids == ['97003966', '103816477']
            assert window.centralWidget().wallpaper_only
        print('PASS actual WPF return button, double round trip, process reuse and modern state')
        window.version_button.click()
        wait_until(lambda: switcher.active_version == 'legacy')
        assert close_native_window(pid)
        wait_until(lambda: bool(closed))
        assert not switcher.is_running
        print('PASS legacy close ends both original applications')
    finally:
        switcher.request_close()
        wait_until(lambda: not switcher.is_running)
        window.session.shutdown()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    legacy_exe = ROOT / 'legacy/dist/win-x64/PixivBatchBookmark.exe'
    child = subprocess.Popen([str(legacy_exe), '--integrated'], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        # Closing the parent's write end simulates a killed supervisor.
        child.stdin.close()
        assert child.wait(timeout=20) == 0
        print('PASS actual WPF gracefully exits on parent pipe EOF')
    finally:
        if child.poll() is None:
            child.kill()  # Test cleanup only; no account/batch exists.
            child.wait()
    package = ROOT / 'dist/PixivBatchBookmark'
    # Chromium may retain file handles until this process exits; use a separate
    # profile for the frozen application rather than sharing the source profile.
    os.environ['LOCALAPPDATA'] = str(Path(data) / 'frozen')
    assert (package / 'legacy/PixivBatchBookmark.exe').is_file()
    assert (package / 'legacy/PixivBatchBookmark.dll').is_file()
    bundled = subprocess.Popen([str(package / 'PixivBatchBookmark.exe'), '--offline'])
    try:
        wait_until(lambda: close_native_window(bundled.pid) or bundled.poll() is not None, timeout=40)
        assert bundled.wait(timeout=20) == 0
        print('PASS complete frozen package starts and exits offline')
    finally:
        if bundled.poll() is None:
            bundled.kill()
            bundled.wait()
print('All unified Windows smoke checks passed.')
