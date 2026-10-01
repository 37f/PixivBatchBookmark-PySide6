"""Local Chromium cookie persistence check across two clean process exits."""

import json
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class Handler(BaseHTTPRequestHandler):
    observed = []

    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path.startswith('/ajax/user/extra'):
            payload = json.dumps({'error': False, 'body': {}}).encode()
            content = 'application/json'
        elif self.path == '/cookie':
            cookie = self.headers.get('Cookie', '')
            self.observed.append(cookie)
            payload = json.dumps({'error': False, 'body': {'cookie': cookie}}).encode()
            content = 'application/json'
        else:
            data = {'userData': {'id': '12345', 'name': 'Fixture'}, 'token': 'fixture'}
            payload = ('<meta id="meta-global-data" content=\'' + json.dumps(data) + '\'>').encode()
            content = 'text/html'
        self.send_response(200)
        self.send_header('Content-Type', content + '; charset=utf-8')
        if self.path == '/seed':
            self.send_header('Set-Cookie', 'pbb_local_fixture=persisted; Path=/; HttpOnly')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def child(profile_path, origin, phase):
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtWidgets import QApplication
    from pixiv.bookmark import Request
    from pixiv.browser import BrowserSession

    app = QApplication([])
    session = BrowserSession(Path(profile_path), base_url=origin)
    result = {'ok': False}

    def logged(ok, _):
        if not ok:
            return
        if phase == 'seed':
            result['ok'] = True
            QTimer.singleShot(400, app.quit)
        else:
            session.request(Request('GET', '/cookie'), checked)

    def checked(response, error):
        result['ok'] = not error and 'pbb_local_fixture=persisted' in response['body']['cookie']
        app.quit()

    session.login_changed.connect(logged)
    app.aboutToQuit.connect(session.shutdown)
    QTimer.singleShot(15000, app.quit)
    session.view.load(QUrl(origin + ('/seed' if phase == 'seed' else '/')))
    app.exec()
    return 0 if result['ok'] else 1


def main():
    if len(sys.argv) == 5 and sys.argv[1] == '--child':
        return child(*sys.argv[2:])
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    with tempfile.TemporaryDirectory(prefix='pbb-cookie-qa-') as directory:
        for phase in ('seed', 'probe'):
            result = subprocess.run([sys.executable, __file__, '--child', directory, origin, phase],
                                    capture_output=True, timeout=25)
            if result.returncode:
                print(f'Cookie {phase} failed: {result.stderr!r}')
                return 1
        assert Handler.observed and 'pbb_local_fixture=persisted' in Handler.observed[-1]
    server.shutdown()
    print('PASS: local HttpOnly session cookie survives a normal exit and second process startup')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
