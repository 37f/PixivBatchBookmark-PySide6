"""Official website login and asynchronous requests in the same browser profile."""

import json
import uuid
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QFile, QIODevice, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript
from PySide6.QtWebEngineWidgets import QWebEngineView

from app_config import resource_path
from pixiv.bookmark import ApiError, Request

WORLD = int(QWebEngineScript.ScriptWorldId.ApplicationWorld)


class Bridge(QObject):
    received = Signal(str, str)

    @Slot(str, str)
    def reply(self, request_id, value):
        self.received.emit(request_id, value)


class LoginPage(QWebEnginePage):
    def createWindow(self, _):
        # OAuth popups reuse the login window, so their cookies stay in this profile.
        popup = QWebEnginePage(self.profile(), self)
        popup.urlChanged.connect(lambda url: self.setUrl(url) if url.scheme() == 'https' else None)
        return popup


class BrowserSession(QObject):
    login_changed = Signal(bool, str)
    message = Signal(str)

    def __init__(self, data_path: Path, parent=None, base_url='https://www.pixiv.net'):
        super().__init__(parent)
        self.base_url = base_url.rstrip('/')
        self.origin = self.base_url
        self.ready = False
        self.logged_in = False
        self.user_id = ''
        self.user_name = ''
        self.timeout_ms = 25000
        self._pending = {}
        self._checking = False
        self._closed = False
        self.profile = QWebEngineProfile('pixiv-session', self)
        self.profile.setPersistentStoragePath(str(data_path / 'browser'))
        self.profile.setCachePath(str(data_path / 'cache'))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.view = QWebEngineView()
        self.page = LoginPage(self.profile, self.view)
        self.view.setPage(self.page)
        self.channel = QWebChannel(self.page)
        self.bridge = Bridge(self.channel)
        self.channel.registerObject('pbbBridge', self.bridge)
        self.page.setWebChannel(self.channel, WORLD)
        self.bridge.received.connect(self._reply)

        channel_js = QFile(':/qtwebchannel/qwebchannel.js')
        if not channel_js.open(QIODevice.OpenModeFlag.ReadOnly):
            raise RuntimeError('无法加载 Qt WebChannel 资源')
        source = bytes(channel_js.readAll()).decode('utf-8')
        channel_js.close()
        source += '\n' + resource_path('bridge.js').read_text(encoding='utf-8').replace('__PBB_ORIGIN__', json.dumps(self.origin))
        script = QWebEngineScript()
        script.setName('PixivBatchBookmark-Bridge')
        script.setWorldId(WORLD)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(source)
        self.page.scripts().insert(script)
        self.page.loadStarted.connect(self._navigation_started)
        self.page.loadFinished.connect(self._load_finished)
        self.page.renderProcessTerminated.connect(lambda *_: self._navigation_started())

    def load_home(self):
        self.view.load(QUrl(self.base_url + '/'))

    def open_login(self):
        self.view.load(QUrl('https://accounts.pixiv.net/login?lang=zh&return_to=https%3A%2F%2Fwww.pixiv.net%2F'))

    def _navigation_started(self):
        self.ready = False
        self.logged_in = False
        self.user_id = ''
        self.user_name = ''
        self.login_changed.emit(False, '正在载入登录页面…')
        pending, self._pending = self._pending, {}
        for callback, timer in pending.values():
            timer.stop()
            timer.deleteLater()
            callback(None, ApiError('页面发生跳转，当前请求状态需人工检查', stop_batch=True))

    def _load_finished(self, ok):
        if not ok:
            self.login_changed.emit(False, '连接失败，请检查网络或代理')

    def _reply(self, request_id, value):
        if self._closed:
            return
        if request_id == '__ready__':
            self.ready = True
            QTimer.singleShot(0, self.check_login)
            return
        pending = self._pending.pop(request_id, None)
        if not pending:
            return
        callback, timer = pending
        timer.stop()
        timer.deleteLater()
        try:
            data = json.loads(value)
            if 'error' in data:
                error = data['error']
                callback(None, ApiError(error.get('message', '请求失败'),
                    status=int(error.get('status', 0)), stop_batch=bool(error.get('fatal'))))
            else:
                callback(data['response'], None)
        except (ValueError, KeyError, TypeError):
            callback(None, ApiError('浏览器返回格式错误', stop_batch=True))

    def request(self, request: Request, callback):
        if self._closed or not self.ready:
            QTimer.singleShot(0, lambda: callback(None, ApiError('浏览器尚未就绪，请打开登录窗口', stop_batch=True)))
            return
        if not request.path.startswith('/') or request.path.startswith('//'):
            raise ValueError('Only same-origin relative requests are allowed')
        request_id = uuid.uuid4().hex
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._expire(request_id))
        self._pending[request_id] = (callback, timer)
        timer.start(self.timeout_ms + 1500)
        payload = {'method': request.method, 'path': request.path, 'data': request.data,
                   'encoding': request.encoding, 'response_type': request.response_type}
        source = f'window.pbbRequest({json.dumps(request_id)}, {json.dumps(payload)}, {self.timeout_ms});'
        self.page.runJavaScript(source, WORLD)

    def _expire(self, request_id):
        pending = self._pending.pop(request_id, None)
        if pending:
            callback, timer = pending
            timer.deleteLater()
            callback(None, ApiError('浏览器请求超时，正在检查最终状态'))

    def check_login(self):
        if self._checking or self._closed:
            return
        if not self.ready:
            if self.view.url().host() != urlparse(self.base_url).hostname:
                self.load_home()
            return
        self._checking = True
        # A refresh invalidates readiness immediately; callers must not start
        # writes while JavaScript is replacing the token from the session check.
        self.logged_in = False
        self.login_changed.emit(False, '正在检查登录状态…')

        def checked(response, error):
            self._checking = False
            if error or response.get('error'):
                self.logged_in = False
                self.user_id = ''
                self.user_name = ''
                self.login_changed.emit(False, str(error or '登录不可用'))
                return
            body = response['body']
            self.logged_in = True
            self.user_id = body['userId']
            self.user_name = body['name']
            self.login_changed.emit(True, f'已登录：{self.user_name}（{self.user_id}）')

        self.request(Request('GET', '/ajax/user/extra', response_type='session'), checked)

    def clear_login(self):
        self.profile.cookieStore().deleteAllCookies()
        self.logged_in = False
        self.user_id = ''
        self.login_changed.emit(False, '已清除本机登录 Cookie，重新启动后生效')
        self.view.setUrl(QUrl('about:blank'))

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        for _, timer in self._pending.values():
            timer.stop()
        self._pending.clear()
        # The page must be destroyed before its persistent profile is flushed.
        self.view.close()
        self.page.deleteLater()
        self.view.deleteLater()
        self.profile.deleteLater()
