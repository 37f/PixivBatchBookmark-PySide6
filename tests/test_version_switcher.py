"""Offline integration tests using real Qt windows and real pipe subprocesses."""

import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QWidget

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        APP.processEvents()
        time.sleep(0.005)
    if not predicate():
        raise AssertionError('Timed out waiting for window/child state')


CHILD = '''
import sys, time
scenario = sys.argv[1]
if scenario == 'timeout':
    time.sleep(30)
elif scenario == 'crash':
    print('READY', flush=True)
    assert sys.stdin.readline().strip() == 'LEGACY'
    print('SHOWN', flush=True)
    time.sleep(.2)
    sys.exit(7)
else:
    # Split readiness across separate OS writes to exercise pipe buffering.
    sys.stdout.write('RE'); sys.stdout.flush(); time.sleep(.01)
    print('ADY', flush=True)
    for line in sys.stdin:
        command = line.strip()
        if command == 'EXIT':
            time.sleep(.05)
            break
        if command == 'LEGACY':
            print('SHOWN', flush=True)
            if scenario == 'hung_after_show':
                time.sleep(30)
        if command == 'RETURN':
            print('MODERN', flush=True)
        if command == 'CLOSE':
            break
'''


class HostWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.controller = SimpleNamespace(running=False)
        self.login_dialog = None
        self.version_button = QPushButton('切换到旧版', self)
        self.switcher = None
        self.closed = False

    def closeEvent(self, event):
        if self.switcher and not self.switcher.request_close():
            event.ignore()
        else:
            self.closed = True
            event.accept()


class VersionSwitcherTests(unittest.TestCase):
    def setUp(self):
        from ui.version_switcher import VersionSwitcher
        self.Switcher = VersionSwitcher
        self.temp = tempfile.TemporaryDirectory(prefix='version test ')
        self.script = Path(self.temp.name) / 'legacy child.py'
        self.script.write_text(CHILD, encoding='utf-8')
        self.window = HostWindow()
        self.window.show()
        self.errors = []

    def make_switcher(self, scenario='normal', **kwargs):
        switcher = self.Switcher(self.window,
            command=[sys.executable, '-u', str(self.script), scenario], **kwargs)
        switcher.failed.connect(self.errors.append)
        self.window.switcher = switcher
        return switcher

    def tearDown(self):
        if self.window.switcher:
            self.window.switcher.request_close()
            wait_until(lambda: not self.window.switcher.is_running)
        self.window.close()
        APP.processEvents()
        self.temp.cleanup()

    def test_round_trip_reuses_process_and_preserves_modern_input(self):
        switcher = self.make_switcher()
        self.window.setWindowTitle('kept input and results')
        switcher.switch_to_legacy()
        switcher.switch_to_legacy()  # A rapid second click must do nothing.
        self.assertTrue(self.window.isVisible())
        wait_until(lambda: switcher.active_version == 'legacy')
        pid = switcher.process.processId()
        self.assertFalse(self.window.isVisible())
        switcher.process.write(b'RETURN\n')
        wait_until(lambda: self.window.isVisible())
        self.assertEqual(switcher.active_version, 'modern')
        self.assertEqual(self.window.windowTitle(), 'kept input and results')
        switcher.switch_to_legacy()
        wait_until(lambda: switcher.active_version == 'legacy')
        self.assertEqual(switcher.process.processId(), pid)
        self.assertFalse(self.errors)

    def test_running_or_paused_batch_and_visible_login_block_switch(self):
        switcher = self.make_switcher()
        self.window.controller.running = True
        switcher.switch_to_legacy()
        self.assertFalse(switcher.is_running)
        self.window.controller.running = False
        self.window.login_dialog = QWidget()
        self.window.login_dialog.show()
        switcher.switch_to_legacy()
        self.assertFalse(switcher.is_running)
        self.window.login_dialog.close()

    def test_missing_binary_keeps_modern_visible_and_can_retry(self):
        switcher = self.Switcher(self.window, command=[str(Path(self.temp.name) / 'missing.exe')])
        switcher.failed.connect(self.errors.append)
        self.window.switcher = switcher
        switcher.switch_to_legacy()
        wait_until(lambda: bool(self.errors))
        self.assertTrue(self.window.isVisible())
        self.assertFalse(switcher.pending)
        self.assertFalse(switcher.is_running)

    def test_timeout_keeps_modern_and_closes_unresponsive_child(self):
        switcher = self.make_switcher('timeout', startup_timeout_ms=100)
        switcher.switch_to_legacy()
        wait_until(lambda: bool(self.errors) and not switcher.is_running)
        self.assertTrue(self.window.isVisible())
        self.assertFalse(switcher.pending)

    def test_close_during_stalled_initial_startup_has_bounded_cleanup(self):
        switcher = self.make_switcher('timeout', startup_timeout_ms=10000,
                                     shutdown_timeout_ms=100)
        switcher.switch_to_legacy()
        wait_until(lambda: switcher.is_running)
        self.window.close()
        wait_until(lambda: self.window.closed, timeout=2)
        self.assertFalse(switcher.is_running)

    def test_crash_restores_modern_instead_of_exiting(self):
        switcher = self.make_switcher('crash')
        switcher.switch_to_legacy()
        wait_until(lambda: switcher.active_version == 'legacy')
        wait_until(lambda: bool(self.errors))
        self.assertTrue(self.window.isVisible())
        self.assertFalse(self.window.closed)

    def test_unresponsive_active_child_recovers_controls_without_force_kill(self):
        switcher = self.make_switcher('hung_after_show', shutdown_timeout_ms=100)
        switcher.switch_to_legacy()
        wait_until(lambda: switcher.active_version == 'legacy')
        self.window.close()
        wait_until(lambda: switcher.shutdown_blocked)
        self.assertTrue(self.window.isVisible())
        self.assertFalse(switcher.pending)
        self.assertTrue(switcher.is_running)
        self.assertFalse(self.window.closed)
        # This fixture contains no task. Test cleanup can kill it safely.
        switcher.process.kill()
        wait_until(lambda: not switcher.is_running)

    def test_normal_legacy_close_ends_unified_app(self):
        switcher = self.make_switcher()
        switcher.switch_to_legacy()
        wait_until(lambda: switcher.active_version == 'legacy')
        switcher.process.write(b'CLOSE\n')
        wait_until(lambda: self.window.closed)
        self.assertFalse(self.errors)

    def test_close_modern_waits_for_hidden_legacy_to_exit(self):
        switcher = self.make_switcher()
        switcher.switch_to_legacy()
        wait_until(lambda: switcher.active_version == 'legacy')
        switcher.process.write(b'RETURN\n')
        wait_until(lambda: self.window.isVisible())
        self.window.close()
        self.assertFalse(self.window.closed)
        wait_until(lambda: self.window.closed)
        self.assertFalse(switcher.is_running)


class FakeSession(QObject):
    login_changed = Signal(bool, str)
    logged_in = False
    user_name = ''
    def __init__(self):
        super().__init__()
        self.view = QWidget()
    def check_login(self): pass
    def open_login(self): pass


class ModernButtonTests(unittest.TestCase):
    def test_one_button_survives_wallpaper_and_disables_while_busy(self):
        from ui.window import MainWindow
        window = MainWindow(session=FakeSession(), offline=True)
        try:
            window.show()
            switches = [b for b in window.findChildren(QPushButton) if b.text() == '切换到旧版']
            self.assertEqual(len(switches), 1)
            window.toggle_wallpaper()
            self.assertTrue(switches[0].isVisible())
            window._set_busy(True)
            self.assertFalse(switches[0].isEnabled())
            window._set_busy(False)
            self.assertTrue(switches[0].isEnabled())
        finally:
            window.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
