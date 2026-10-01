"""Windows entry point. Use --offline to inspect the UI without connecting."""

import argparse
import sys
from urllib.parse import urlparse

from PySide6.QtCore import QCoreApplication, QLockFile
from PySide6.QtGui import QFont, QIcon
from PySide6.QtNetwork import QNetworkProxy, QNetworkProxyFactory
from PySide6.QtWidgets import QApplication, QMessageBox

from app_config import APP_NAME, VERSION, load_settings, resource_path, user_data_dir


def apply_proxy(value):
    if not value:
        QNetworkProxyFactory.setUseSystemConfiguration(True)
        return
    parsed = urlparse(value)
    if parsed.scheme not in ('http', 'socks5') or not parsed.hostname or not parsed.port:
        raise ValueError('代理地址无效，请检查 settings.json 中的 proxy。')
    kind = QNetworkProxy.ProxyType.HttpProxy if parsed.scheme == 'http' else QNetworkProxy.ProxyType.Socks5Proxy
    QNetworkProxy.setApplicationProxy(QNetworkProxy(kind, parsed.hostname, parsed.port))


def main():
    parser = argparse.ArgumentParser(description=f'PixivBatchBookmark Windows v{VERSION}')
    parser.add_argument('--offline', action='store_true', help='启动时不连接 Pixiv，可检查界面和 ID 解析')
    args = parser.parse_args()
    QCoreApplication.setApplicationName(APP_NAME)
    QCoreApplication.setOrganizationName(APP_NAME)
    QCoreApplication.setApplicationVersion(VERSION)
    app = QApplication(sys.argv[:1])
    app.setFont(QFont('Microsoft YaHei UI', 10))
    app.setWindowIcon(QIcon(str(resource_path('icon.ico'))))
    lock = QLockFile(str(user_data_dir() / 'app.lock'))
    if not lock.tryLock(0):
        QMessageBox.information(None, '程序已经打开', '请使用已打开的 PixivBatchBookmark 窗口。')
        return 0
    try:
        apply_proxy(load_settings()['proxy'])
        from ui.window import MainWindow
        window = MainWindow(offline=args.offline)
    except Exception as error:
        QMessageBox.critical(None, '启动失败', str(error))
        lock.unlock()
        return 1
    app.aboutToQuit.connect(window.session.shutdown)
    window.show()
    result = app.exec()
    lock.unlock()
    return result


if __name__ == '__main__':
    raise SystemExit(main())
