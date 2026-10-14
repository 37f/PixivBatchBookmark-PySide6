# Unified integration verification

Source baselines:
- PySide6: `e25f28fb2302b9d3495f7b687077d7457b39d55b`.
- Original WPF: `31fdab1735593899ec40bb6f78ab4c1d450a8186`.

Local Linux verification: original Python suite 21/21; expanded suite 31/31,
including real QProcess pipes, split readiness, process reuse, missing executable,
timeout, crash recovery, busy/login guard, normal legacy close, coordinated parent
close, stalled-startup close recovery, safe active-child close timeout and the
visible wallpaper-mode button. Qt uses offscreen rendering here.

Original legacy core tests: 56/56 passed using .NET SDK 10.0.402.
Cross-compilation of the integrated WPF app and extended WPF UiSmoke project:
successful, 0 warnings and 0 errors, with EnableWindowsTargeting=true.
Cross-compilation verifies C#/XAML compilation, not Windows UI execution.

Independent review found two material shutdown issues. Regression coverage and
implementation now address Windows console-child timeout cleanup and stalled
startup close; an active/unresponsive child is not force-killed. The WPF app
stays hidden until host activation, and modern controls recover on unsafe-close
timeout while bookmark writes and switching remain blocked until child exit.

Windows workflow runs both business suites, original WPF UI smoke extended with
the return button, busy guard and state preservation; builds both complete apps;
uses Windows UI Automation to click the actual WPF return button twice; checks
parent EOF, normal legacy close, frozen package startup and portable ZIP output.
GitHub write APIs returned 403 for branch/tree creation in this session; no PR or
Windows workflow was started. The workflow is included for use after uploading
the source. Actual Windows UI and frozen-package acceptance remain pending.

No real Pixiv login or bookmark mutation is included in these tests. Each engine
retains its existing business logic and separate persistent browser configuration.
