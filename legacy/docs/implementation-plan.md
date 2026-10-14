# Pixiv 批量收藏 Windows 版实施计划

目标：按 design.md 交付中文桌面项目、可运行发布包、测试与构建说明。
架构：无 UI 依赖的 Core 处理输入和收藏状态；WPF 项目负责登录和任务展示；离线控制台测试不连接真实账号。
技术：.NET 10、WPF、Microsoft.Web.WebView2 1.0.4258.31。

全局约束：顺序执行；作品之间间隔 1.5 秒；请求超时 30 秒；无写请求自动重试；不输出 Cookie、密码或安全令牌。

## 1. 解析与收藏逻辑

- [x] 编写失败测试：URL/标注/纯 ID 解析、排除用户与小说 URL、去重、两向模式转换、同模式跳过、批量取消、恢复原收藏。
- [x] 建立 Core 接口 `IPixivClient`，实现 `IdParser.Parse` 和 `BookmarkService.ProcessAsync`。
- [x] 跑离线测试，确认状态与调用顺序满足设计。

## 2. Pixiv HTTP 与认证

- [x] 编写失败测试：global-data / 转义 JSON 令牌解析、收藏状态、原标签、添加 JSON、删除表单、401/403/429、异常响应。
- [x] 实现 `PixivHttpClient` 与 `SessionParser`；独立的 HttpMessageHandler 夹具核对线上边界。
- [x] 跑全套测试。

## 3. Windows 界面与分发

- [x] 实现官方网页登录窗口、互斥收藏模式、输入预览、日志、进度与停止。
- [x] 编译 WPF 并发布 win-x64 自包含程序。
- [x] 启动发布程序，检查窗口、解析和模式切换；记录未覆盖的真实账号验收。
- [x] 写中文 README、build.ps1/build.bat、测试命令与版本/验证记录，生成源码 ZIP 和便携 ZIP。

重点审查：来源不明的 URL 数字不应误提交；令牌缺失不应启动批次；标签读取失败不应取消原收藏；取消/添加返回成功但状态不符不应算成功；停止不应切断模式转换。
