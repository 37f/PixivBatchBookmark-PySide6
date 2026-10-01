"""Serial, nonblocking task driver; pause/stop happen at artwork boundaries."""

from PySide6.QtCore import QObject, QTimer, Signal

from pixiv.bookmark import ApiError, BookmarkService, ItemResult


class BatchController(QObject):
    item_done = Signal(object)
    progress = Signal(int, int)
    state_changed = Signal(str)
    finished = Signal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.service = BookmarkService()
        self.interval_ms = 1200
        self.running = False
        self.paused = False
        self.stopping = False
        self.results = []
        self._flow = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._send_pending)

    def start(self, ids, action, private):
        if self.running:
            raise RuntimeError('A batch is already active')
        if not ids:
            raise ValueError('A batch requires artwork IDs')
        self.ids = list(ids)
        self.action = action
        self.private = private
        self.results = []
        self.index = 0
        self.running = True
        self.paused = self.stopping = False
        self.state_changed.emit('任务进行中')
        self.progress.emit(0, len(self.ids))
        QTimer.singleShot(0, self._next_item)

    def _next_item(self):
        # Resume and a queued boundary callback can arrive in the same tick.
        # Never replace a live generator while its browser request is in flight.
        if not self.running or self._flow is not None:
            return
        if self.stopping or self.index == len(self.ids):
            return self._finish()
        if self.paused:
            self.state_changed.emit('已暂停')
            return
        self._flow = self.service.apply_one(self.ids[self.index], self.action, self.private)
        self._advance()

    def _advance(self, response=None, error=None):
        try:
            request = self._flow.throw(error) if error else self._flow.send(response)
        except StopIteration as completed:
            result = completed.value
            self.results.append(result)
            self.item_done.emit(result)
            self.index += 1
            self.progress.emit(self.index, len(self.ids))
            self._flow = None
            if result.stop_batch:
                self.stopping = True
                self.state_changed.emit('异常停止：请检查登录、网络或作品状态')
            QTimer.singleShot(0, self._next_item)
        except Exception as unexpected:
            # Unknown exceptions must never be converted into a success.
            result = ItemResult(self.ids[self.index], 'failed', '任务异常：' + str(unexpected), True)
            self.results.append(result)
            self.item_done.emit(result)
            self.index += 1
            self.progress.emit(self.index, len(self.ids))
            self.stopping = True
            self._finish()
        else:
            self._pending_request = request
            self._timer.start(self.interval_ms)

    def _send_pending(self):
        self.session.request(self._pending_request, self._advance)

    def toggle_pause(self):
        if not self.running:
            return
        self.paused = not self.paused
        if self.paused:
            self.state_changed.emit('正在完成当前作品，随后暂停…' if self._flow else '已暂停')
        else:
            self.state_changed.emit('任务进行中')
            if self._flow is None:
                self._next_item()

    def stop(self):
        if self.running:
            self.stopping = True
            self.state_changed.emit('正在完成当前作品，随后停止…')
            if self._flow is None:
                self._finish()

    def _finish(self):
        if not self.running:
            return
        self.running = False
        self._flow = None
        self.paused = False
        self._timer.stop()
        self.finished.emit()
