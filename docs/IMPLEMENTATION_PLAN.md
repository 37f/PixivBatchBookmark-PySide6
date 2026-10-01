# PixivBatchBookmark Windows v1.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 交付可构建的 Windows 源码、用户图片资源和中文说明。

**Architecture:** 独立业务生成器 + Chromium 同源请求 + Qt 串行控制器。共享浏览器会话负责认证，UI 保持响应。

**Tech Stack:** Python 3.12，PySide6 6.10.2，PyInstaller 6.22.0，Pillow 12.1.0（仅资源构建）。

**Spec:** [DESIGN.md](DESIGN.md)

## Global Constraints

- 不在真实账号上自动执行收藏或取消操作。
- 作品 ID 支持插画、漫画、动图，小说和用户链接排除。
- 公开/私密转换先取消再重建，保留可读取的原标签与备注。
- 背景：狐耳女孩竖图；图标：小女孩方图；保留原图。
- 运行时用户数据放在本机 LocalAppData 独立目录；源码包不包含用户会话。

## Review Focus

- 混合文本中的日期、作者 ID、小说 ID 不可误导入为作品。
- 缺少 bookmarkData/private 字段不等于未收藏。
- 写入超时需先读取状态，不能盲目重发。
- 转换过程中停止应在恢复/核验后生效。
- 打包后浏览器辅助进程、资源路径、Cookie 保存生命周期都可正常工作。

## Task 1: 输入与收藏核心

Files: pixiv/parser.py, pixiv/bookmark.py, tests/test_parser.py, tests/test_bookmark.py。

Interfaces: parse_ids(text: str) -> list[str]；BookmarkService.apply_one(illust_id, action, private) -> Generator[Request, dict, ItemResult]。

- [x] 先写解析/跳过/转换/失败恢复测试，运行 unittest 确认缺少实现。
- [x] 实现 ID 提取、响应校验和请求生成器。
- [x] 运行全部核心测试，要求零失败。

## Task 2: 浏览器与界面

Files: pixiv/browser.py, resources/bridge.js, ui/controller.py, ui/window.py, app_config.py, main.py, tests/qt_smoke.py。

Interfaces: BrowserSession.request(Request, callback)，callback(response, error)；BatchController.start(ids, action, private)。

- [x] 写 Qt 离线集成测试，本地 fixture 提供 Pixiv 格式响应。
- [x] 实现持久化 profile、隔离 WebChannel、官方网页登录与同源请求。
- [x] 实现主窗口与串行任务控制、统计、暂停停止、文件与代理操作。
- [x] 验证真实 Chromium 接口路径、CSRF、表单、异常，以及主窗口截图。

## Task 3: 构建与交付

Files: requirements*.txt, PixivBatchBookmark.spec, run.bat, build.bat, scripts/prepare_resources.py, README.md。

- [x] 复制原图并转换图标；写中文运行与构建说明。
- [x] 实际执行单目录 PyInstaller 构建；启动打包程序检查入口、主窗口和 Chromium 辅助进程。
- [x] 复核项目需求，排除会话和缓存，生成源码 ZIP 与验证记录。
