"""Chinese desktop UI with the supplied wallpaper and application icon."""

import csv
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QGroupBox, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QRadioButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)

from app_config import VERSION, load_settings, resource_path, save_settings, user_data_dir
from pixiv.browser import BrowserSession
from pixiv.parser import parse_ids
from ui.controller import BatchController

STYLE = '''
QWidget { font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif; font-size: 13px; color: #293647; }
QLabel { background: transparent; }
QLabel#title { font-size: 25px; font-weight: bold; color: #184975; }
QLabel#muted { color: #576b7b; }
QGroupBox { background: rgba(255,255,255,215); border: 1px solid rgba(255,255,255,245);
    border-radius: 14px; margin-top: 15px; padding: 20px 14px 12px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 17px; padding: 0 5px; }
QPushButton { background: rgba(255,255,255,232); border: 1px solid #c4d5df;
    border-radius: 8px; padding: 8px 14px; min-height: 20px; }
QPushButton:hover { background: #e4f2fc; border-color: #6aabd9; }
QPushButton:pressed { background: #c6e5fb; }
QPushButton:disabled { color: #91a1ac; background: rgba(238,241,243,220); }
QPushButton#primary { background: #258acb; color: white; border-color: #258acb; font-weight: bold; }
QPushButton#primary:hover { background: #1679ba; }
QPushButton#primary:disabled { background: #96b6cb; border-color: #96b6cb; }
QPushButton#danger { color: #b74747; border-color: #d5aaaa; }
QPlainTextEdit, QTableWidget { background: rgba(255,255,255,208); border: 1px solid #c7d6df;
    border-radius: 8px; padding: 7px; font-weight: normal; selection-background-color: #b1dcf7; }
QHeaderView::section { background: #e8f1f8; color: #38566a; padding: 6px; border: none; }
QRadioButton { background: transparent; padding: 6px; font-weight: normal; }
QProgressBar { border: 1px solid #c4d5df; border-radius: 6px; text-align: center;
    background: rgba(255,255,255,225); min-height: 22px; }
QProgressBar::chunk { background: #76b7dc; border-radius: 5px; }
QSplitter::handle { background: transparent; width: 14px; }
'''


class ThemeWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.background = QPixmap(str(resource_path('background.png')))
        self.wallpaper_only = False

    def set_wallpaper_only(self, enabled):
        self.wallpaper_only = enabled
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.wallpaper_only:
            painter.fillRect(self.rect(), QColor(42, 33, 35))
        if not self.background.isNull():
            # 展示模式保留完整原图；正常模式继续填满窗口，作为控件背景。
            aspect = (Qt.AspectRatioMode.KeepAspectRatio if self.wallpaper_only
                      else Qt.AspectRatioMode.KeepAspectRatioByExpanding)
            image = self.background.scaled(self.size(), aspect,
                                           Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap((self.width() - image.width()) // 2, (self.height() - image.height()) // 2, image)
        if not self.wallpaper_only:
            painter.fillRect(self.rect(), QColor(238, 244, 249, 105))
        painter.end()


class InputEdit(QPlainTextEdit):
    files_dropped = Signal(list)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self.files_dropped.emit([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


def button(label, callback, name=''):
    result = QPushButton(label)
    result.setObjectName(name)
    result.clicked.connect(callback)
    return result


class MainWindow(QMainWindow):
    def __init__(self, session=None, offline=False):
        super().__init__()
        self.setWindowTitle(f'PixivBatchBookmark Windows v{VERSION}')
        self.setWindowIcon(QIcon(str(resource_path('icon.ico'))))
        self.resize(1160, 820)
        self.setMinimumSize(960, 720)
        self.setStyleSheet(STYLE)
        self.settings = load_settings()
        self.ids = []
        self.session = session or BrowserSession(user_data_dir(), self)
        self.controller = BatchController(self.session, self)
        self.controller.interval_ms = self.settings['interval_ms']
        self.login_dialog = None
        self._make_ui()
        self.session.login_changed.connect(self._login_changed)
        self.controller.item_done.connect(self._item_done)
        self.controller.progress.connect(self._progress)
        self.controller.state_changed.connect(self.task_label.setText)
        self.controller.finished.connect(self._finished)
        self._login_changed(self.session.logged_in, '已登录：' + self.session.user_name if self.session.logged_in
                            else '尚未登录 · 点击“登录 Pixiv”')
        self.log('就绪。先解析作品 ID，再登录并选择收藏操作。')
        if offline:
            self.log('离线启动：可检查界面和解析；点击登录后连接 Pixiv。')
        elif session is None:
            self.session.load_home()

    def _make_ui(self):
        central = ThemeWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(10)
        self.wallpaper_button = button('看看兽娘麻麻˃ 𖥦 ˂ ', self.toggle_wallpaper)
        # 颜文字的补充平面字符由 Windows Historic 字体补齐，避免显示为方框。
        self.wallpaper_button.setStyleSheet('font-family: "Microsoft YaHei UI", "Segoe UI Historic", "Segoe UI";')
        self.wallpaper_button.setToolTip('隐藏操作界面，展示完整壁纸；再次点击恢复界面')
        outer.addWidget(self.wallpaper_button, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        # 只隐藏操作区域，保留同一个窗口和按钮，输入及运行中的任务不受影响。
        self.interface = QWidget()
        outer.addWidget(self.interface, 1)
        layout = QVBoxLayout(self.interface)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(str(resource_path('icon.png'))).scaled(58, 58, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation))
        header.addWidget(logo)
        titles = QVBoxLayout()
        title = QLabel('Pixiv Batch Bookmark')
        title.setObjectName('title')
        titles.addWidget(title)
        subtitle = QLabel(f'Windows v{VERSION}  ·  让收藏整理更轻松')
        subtitle.setObjectName('muted')
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()
        self.proxy_button = button('代理设置', self.proxy_settings)
        header.addWidget(self.proxy_button)
        layout.addLayout(header)

        login_card = QGroupBox('登录与连接')
        login_layout = QHBoxLayout(login_card)
        self.login_label = QLabel()
        self.login_label.setWordWrap(True)
        login_layout.addWidget(self.login_label, 1)
        self.login_button = button('登录 Pixiv', self.show_login)
        self.refresh_button = button('检查登录', self.session.check_login)
        self.clear_login_button = button('清除登录', self.clear_login)
        login_layout.addWidget(self.login_button)
        login_layout.addWidget(self.refresh_button)
        login_layout.addWidget(self.clear_login_button)
        layout.addWidget(login_card)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        input_card = QGroupBox('作品 ID')
        input_layout = QVBoxLayout(input_card)
        hint = QLabel('支持作品链接、纯 ID 列表或 pixiv id：123 的混合文本')
        hint.setWordWrap(True)
        hint.setObjectName('muted')
        input_layout.addWidget(hint)
        self.input_edit = InputEdit()
        self.input_edit.setPlaceholderText('97003966\n103816477\n\n或粘贴 https://www.pixiv.net/artworks/97003966')
        self.input_edit.files_dropped.connect(self.import_files)
        self.input_edit.textChanged.connect(self._invalidate_ids)
        input_layout.addWidget(self.input_edit, 1)
        tools = QHBoxLayout()
        self.parse_button = button('解析 ID', self.parse_input)
        self.paste_button = button('粘贴', self.paste_input)
        self.import_button = button('导入 TXT', self.import_txt)
        self.clear_button = button('清空', self.input_edit.clear)
        for widget in (self.parse_button, self.paste_button, self.import_button, self.clear_button):
            tools.addWidget(widget)
        input_layout.addLayout(tools)
        self.id_count = QLabel('待解析')
        self.id_count.setObjectName('muted')
        input_layout.addWidget(self.id_count)
        left_layout.addWidget(input_card, 1)

        action_card = QGroupBox('批量操作')
        actions = QVBoxLayout(action_card)
        modes = QHBoxLayout()
        self.public_radio = QRadioButton('公开收藏')
        self.private_radio = QRadioButton('私密收藏')
        self.public_radio.setChecked(True)
        modes.addWidget(self.public_radio)
        modes.addWidget(self.private_radio)
        modes.addStretch()
        actions.addLayout(modes)
        self.bookmark_button = button('开始批量收藏', lambda: self.start_batch('bookmark'), 'primary')
        self.remove_button = button('批量取消收藏', lambda: self.start_batch('remove'), 'danger')
        actions.addWidget(self.bookmark_button)
        actions.addWidget(self.remove_button)
        note = QLabel('同模式跳过；模式不同先取消再收藏。\n暂停或停止会先完成当前作品的核验/恢复。')
        note.setObjectName('muted')
        note.setWordWrap(True)
        actions.addWidget(note)
        left_layout.addWidget(action_card)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        results_card = QGroupBox('任务进度与结果')
        results_layout = QVBoxLayout(results_card)
        self.task_label = QLabel('等待开始')
        results_layout.addWidget(self.task_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        results_layout.addWidget(self.progress_bar)
        self.summary_label = QLabel('成功 0    跳过 0    失败 0')
        results_layout.addWidget(self.summary_label)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['作品 ID', '结果', '说明'])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        results_layout.addWidget(self.table, 1)
        task_tools = QHBoxLayout()
        self.pause_button = button('暂停', self.pause)
        self.stop_button = button('停止', self.controller.stop)
        self.export_button = button('导出结果', self.export_results)
        for widget in (self.pause_button, self.stop_button, self.export_button):
            task_tools.addWidget(widget)
        results_layout.addLayout(task_tools)
        right_layout.addWidget(results_card, 3)

        log_card = QGroupBox('日志')
        log_layout = QVBoxLayout(log_card)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(10000)
        log_layout.addWidget(self.log_edit, 1)
        log_tools = QHBoxLayout()
        log_tools.addStretch()
        log_tools.addWidget(button('保存日志', self.save_log))
        log_layout.addLayout(log_tools)
        right_layout.addWidget(log_card, 2)
        splitter.addWidget(right)
        splitter.setSizes([460, 620])
        layout.addWidget(splitter, 1)
        footer = QLabel('仅处理输入的作品 · 操作结果逐项核验 · 登录信息保存在此电脑')
        footer.setObjectName('muted')
        layout.addWidget(footer)
        self._set_busy(False)

    def toggle_wallpaper(self):
        central = self.centralWidget()
        showing = not central.wallpaper_only
        central.set_wallpaper_only(showing)
        self.interface.setVisible(not showing)
        self.wallpaper_button.setText('再见兽娘麻麻⊙﹏⊙' if showing else '看看兽娘麻麻˃ 𖥦 ˂ ')

    def log(self, text):
        self.log_edit.appendPlainText(f'[{datetime.now():%H:%M:%S}] {text}')

    def _invalidate_ids(self):
        self.ids = []
        self.id_count.setText('输入已变化，等待解析')

    def parse_input(self):
        self.ids = parse_ids(self.input_edit.toPlainText())
        self.id_count.setText(f'已提取 {len(self.ids)} 个作品 ID（已去重）')
        self.log(f'解析完成：{len(self.ids)} 个作品 ID。')

    def paste_input(self):
        self.input_edit.insertPlainText(QApplication.clipboard().text())
        self.parse_input()

    def import_txt(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '导入作品列表', '', '文本文件 (*.txt);;所有文件 (*)')
        if paths:
            self.import_files(paths)

    def import_files(self, paths):
        for value in paths:
            try:
                path = Path(value)
                if path.suffix.lower() != '.txt':
                    raise ValueError('请拖入 TXT 文件')
                if path.stat().st_size > 2 * 1024 * 1024:
                    raise ValueError('TXT 文件超过 2 MB，请分批导入')
                raw = path.read_bytes()
                if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
                    text = raw.decode('utf-16')
                else:
                    try:
                        text = raw.decode('utf-8-sig')
                    except UnicodeDecodeError:
                        text = raw.decode('gb18030')
                self.input_edit.appendPlainText(text)
                self.log(f'已导入 {path.name}')
            except (OSError, UnicodeError, ValueError) as error:
                QMessageBox.warning(self, '导入失败', str(error))
        self.parse_input()

    def _login_changed(self, logged_in, text):
        self.login_label.setText(('● ' if logged_in else '○ ') + text)
        self.login_label.setStyleSheet('color: #276e52;' if logged_in else 'color: #78532f;')

    def show_login(self):
        if self.login_dialog is None:
            self.login_dialog = QDialog(self)
            self.login_dialog.setWindowTitle('登录 Pixiv · 使用官方网站')
            self.login_dialog.resize(1040, 780)
            layout = QVBoxLayout(self.login_dialog)
            theme = ThemeWidget()
            theme_layout = QHBoxLayout(theme)
            theme_layout.addWidget(QLabel('请在官方网站完成登录，成功后点击“返回首页并检查”。'), 1)
            theme_layout.addWidget(button('打开登录页', self.session.open_login))
            theme_layout.addWidget(button('返回首页并检查', self.session.load_home))
            layout.addWidget(theme)
            layout.addWidget(self.session.view, 1)
            layout.addWidget(button('完成，返回主界面', self.login_dialog.hide))
        self.login_dialog.show()
        self.login_dialog.raise_()
        if not self.session.logged_in:
            self.session.open_login()

    def clear_login(self):
        if QMessageBox.question(self, '清除登录', '清除这台电脑保存的 Pixiv 登录 Cookie？') == QMessageBox.StandardButton.Yes:
            self.session.clear_login()
            self.log('已请求清除登录 Cookie。')

    def proxy_settings(self):
        value, accepted = QInputDialog.getText(self, '代理设置',
            '留空使用系统网络；或填写本机代理，例如：\nhttp://127.0.0.1:7890 或 socks5://127.0.0.1:1080\n保存后重启软件生效。',
            text=self.settings['proxy'])
        if not accepted:
            return
        value = value.strip()
        try:
            if value:
                parsed = urlparse(value)
                if (parsed.scheme not in ('http', 'socks5') or not parsed.hostname or not parsed.port
                        or parsed.username or parsed.password or parsed.path not in ('', '/')
                        or parsed.query or parsed.fragment):
                    raise ValueError('使用 http://地址:端口 或 socks5://地址:端口；不支持账号密码。')
            self.settings['proxy'] = value
            save_settings(self.settings)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, '代理设置未保存', str(error))
            return
        self.log('代理设置已保存，重启软件后生效。')
        QMessageBox.information(self, '已保存', '请关闭并重新打开软件，使代理设置生效。')

    def start_batch(self, action):
        self.parse_input()
        if not self.ids:
            QMessageBox.information(self, '没有作品 ID', '请粘贴作品链接、数字列表或带 ID 标记的文本。')
            return
        if not self.session.logged_in:
            QMessageBox.information(self, '请先登录', '请先完成 Pixiv 登录并检查登录状态。')
            self.show_login()
            return
        if action == 'remove':
            confirm = QMessageBox.question(self, '批量取消收藏',
                f'将取消输入列表中 {len(self.ids)} 个作品的收藏。公开与私密均会取消，未收藏会跳过。\n确定开始？')
            if confirm != QMessageBox.StandardButton.Yes:
                return
        elif QMessageBox.question(self, '开始收藏',
                f'将处理 {len(self.ids)} 个作品，目标为{"私密" if self.private_radio.isChecked() else "公开"}收藏。\n'
                '不同模式会先取消再重建，收藏时间和收藏 ID 会变化。\n确定开始？') != QMessageBox.StandardButton.Yes:
            return
        self.table.setRowCount(0)
        self.summary_label.setText('成功 0    跳过 0    失败 0')
        self._set_busy(True)
        self.log(f'开始任务：{len(self.ids)} 个作品，操作：' + ('取消收藏' if action == 'remove' else '收藏'))
        self.controller.start(self.ids, action, self.private_radio.isChecked())

    def _set_busy(self, busy):
        for widget in (self.input_edit, self.parse_button, self.paste_button, self.import_button,
                self.clear_button, self.bookmark_button, self.remove_button, self.public_radio,
                self.private_radio, self.login_button, self.refresh_button, self.clear_login_button, self.proxy_button):
            widget.setEnabled(not busy)
        self.pause_button.setEnabled(busy)
        self.stop_button.setEnabled(busy)
        self.export_button.setEnabled(not busy)
        if self.login_dialog:
            self.login_dialog.setEnabled(not busy)

    def pause(self):
        self.controller.toggle_pause()
        self.pause_button.setText('继续' if self.controller.paused else '暂停')

    def _progress(self, completed, total):
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(completed)
        self.progress_bar.setFormat(f'{completed} / {total}')

    def _item_done(self, result):
        labels = {'success': '成功', 'skipped': '跳过', 'failed': '失败'}
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, text in enumerate((result.illust_id, labels[result.status], result.message)):
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            self.table.setItem(row, column, item)
        self.table.scrollToBottom()
        counts = {key: sum(r.status == key for r in self.controller.results) for key in labels}
        self.summary_label.setText(f'成功 {counts["success"]}    跳过 {counts["skipped"]}    失败 {counts["failed"]}')
        self.log(f'{result.illust_id} · {labels[result.status]} · {result.message}')

    def _finished(self):
        self._set_busy(False)
        self.pause_button.setText('暂停')
        remaining = len(self.controller.ids) - self.controller.index
        text = f'已停止，剩余 {remaining} 个作品未处理' if remaining else '任务完成'
        self.task_label.setText(text)
        self.log(text + '。' + self.summary_label.text())

    def export_results(self):
        if not self.controller.results:
            QMessageBox.information(self, '无结果', '请先执行任务。')
            return
        path, _ = QFileDialog.getSaveFileName(self, '导出结果', 'Pixiv结果.csv', 'CSV 文件 (*.csv)')
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8-sig', newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow(['作品ID', '结果', '说明'])
                for result in self.controller.results:
                    # Avoid spreadsheet formula interpretation of server-provided text.
                    values = [result.illust_id, result.status, result.message]
                    writer.writerow(["'" + value if value.startswith(('=', '+', '-', '@')) else value for value in values])
                for illust_id in self.controller.ids[len(self.controller.results):]:
                    writer.writerow([illust_id, 'unprocessed', '未处理'])
            self.log('结果已导出。')
        except OSError as error:
            QMessageBox.warning(self, '导出失败', str(error))

    def save_log(self):
        path, _ = QFileDialog.getSaveFileName(self, '保存日志', 'Pixiv日志.txt', '文本文件 (*.txt)')
        if path:
            try:
                Path(path).write_text(self.log_edit.toPlainText(), encoding='utf-8-sig')
            except OSError as error:
                QMessageBox.warning(self, '保存失败', str(error))

    def closeEvent(self, event):
        if self.controller.running:
            self.controller.stop()
            QMessageBox.information(self, '等待当前作品完成', '已请求停止。当前作品的核验/恢复结束后，请再关闭窗口。')
            event.ignore()
        else:
            if self.login_dialog:
                self.login_dialog.hide()
            event.accept()
