# Unified versions implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement task by task.

**Goal:** One Windows package retaining both original apps with one button in each to switch.

**Architecture:** Qt manages lifetime and an on-demand WPF child. Anonymous stdio pipes coordinate visibility without transferring user data.

**Tech stack:** Python 3.12, PySide6 6.10.2, C# WPF, .NET 10.

**Spec:** `docs/superpowers/specs/2026-10-14-unified-versions.md`.

## Global constraints

- Retain actual WPF UI, assets, logic and browser profile.
- Default to modern; one switching button per interface, visible in wallpaper mode.
- Never switch during a running/paused batch or interrupt a write to close.
- Preserve WPF assembly name PixivBatchBookmark and ship complete runtimes.

## Review focus

- Missing/unresponsive legacy must leave modern usable.
- Repeated clicks and partial pipe reads must not duplicate processes or writes.
- Legacy crash restores modern; normal close ends both.
- Parent death closes legacy gracefully after busy work completes.
- Paths with spaces, wallpaper mode and modal login must work.

### Task 1: Coordinator and modern UI

Files: `ui/version_switcher.py`, `ui/window.py`, `main.py`, `tests/test_version_switcher.py`.
Interface: `VersionSwitcher(window, command=None, startup_timeout_ms=15000)`,
`switch_to_legacy()`, `request_close() -> bool`, `pending` property.

- [ ] Test real local child-process switching/reuse, busy guards, missing binary,
  timeout, crash, normal exit and asynchronous close; watch RED.
- [ ] Implement QProcess lifecycle and Qt UI wiring; run GREEN and Python suite.
- [ ] Commit coordinator and modern UI.

### Task 2: Retain and integrate WPF

Files: import pinned old source under `legacy/`; new `IntegratedHost.cs`;
modify App.xaml(.cs), MainWindow.xaml(.cs), WPF UiSmoke.
Interface: `EnableIntegratedMode(Action returnToModern)`, `RequestHostClose()`.
Loaded hides and sends READY; return button sends MODERN; LEGACY restores and SHOWN;
EXIT/EOF requests graceful close.

- [ ] Retain original source/resources/licenses and record commit provenance.
- [ ] Add WPF assertions for button, state retention and busy close behavior.
- [ ] Implement pipe reader, integrated startup, busy guard and graceful EOF.
- [ ] Run core/WPF tests in Windows CI and commit.

### Task 3: Unified build and verification

Files: build.ps1, build.bat, run.bat, Windows workflow, README, validation docs,
Windows cross-framework smoke.
Output: `dist/PixivBatchBookmark/PixivBatchBookmark.exe` and complete `legacy/`.

- [ ] Implement unified publish and source startup; preserve third-party notices.
- [ ] Add Windows CI for business suites, WPF UI, real switching and package.
- [ ] Document separate logins, switching and build prerequisites.
- [ ] Run verification, independent code review, fix material findings, draft PR.
