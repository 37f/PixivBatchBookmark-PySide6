# 把融合版提交到新仓库

本次交付包含完整融合源码，以及相对于新版原始提交
`e25f28fb2302b9d3495f7b687077d7457b39d55b` 的二进制安全补丁。
GitHub 写入接口在此次会话返回 403，因此没有修改线上 main 或创建 PR。

## 在电脑上提交

先克隆新仓库，确认没有未提交的个人修改，然后在仓库目录执行：

```powershell
git switch -c feat/unified-legacy-switch
git apply --check C:\路径\PixivBatchBookmark_Unified_v1.1.0.patch
git apply --binary C:\路径\PixivBatchBookmark_Unified_v1.1.0.patch
git add .
git commit -m "feat: unify original WPF and PySide6 versions"
git push -u origin feat/unified-legacy-switch
```

随后在 GitHub 为该分支创建 PR。新加入的 Windows workflow 会自动构建两个
版本并验证切换；通过后可下载完整便携包，运行外层 PixivBatchBookmark.exe。
源码也可以直接解压，在 Windows x64 安装 Python 3.12 和 .NET 10 SDK 后
双击 build.bat 构建。旧版网页登录需 WebView2 Runtime。

如果 main 已经更新，先执行 `git apply --check`；有冲突时需结合最新源码处理，
不要强行覆盖其他修改。旧仓库不用删除，完整原始旧版已经收录在 legacy/。

## 本次验证

Python 31 项、原 C# 核心 56 项测试通过；WPF 主程序和 UI 冒烟项目编译通过。
完整 Windows UI 执行和冻结发布包验证仍待 Windows workflow 或本机执行。
源码 ZIP 不是可直接双击的 EXE 发布包。
