# Third-party components

This project uses original application code with the following dependencies:

- Microsoft .NET 10 / WPF: https://github.com/dotnet/runtime and https://github.com/dotnet/wpf (MIT and included third-party notices in the upstream distributions).
- Microsoft.Web.WebView2 1.0.4258.31: https://www.nuget.org/packages/Microsoft.Web.WebView2/1.0.4258.31 (Microsoft WebView2 SDK license applies).
- Microsoft Edge WebView2 Runtime: installed separately under Microsoft's runtime license. https://developer.microsoft.com/en-us/microsoft-edge/webview2/

The project is unaffiliated with Pixiv. Pixiv owns its service, logos and website content; artwork rights belong to their respective creators.

Version 1.0.1 bundles the user-supplied icon image and theme wallpaper as UI assets. These images retain their creators' rights. The wallpaper's visible attribution is @cloneko.oo. The original images and their visible credit are preserved; the application dependency licenses do not grant artwork rights.

Version 1.0.4 adds a second user-supplied wallpaper in its original JPEG format. Its original pixels and visible creator signature are preserved. The artwork remains subject to its creator's rights.

Endpoint request formats were checked against original open-source implementations, without copying their code:
https://github.com/AgMonk/pixiv-utils
https://github.com/xuejianxianzun/PixivBatchDownloader
https://github.com/ppixiv/ppixiv

Pixiv bookmark behavior reference:
https://www.pixiv.help/hc/en-us/articles/235646967-What-are-Bookmarks
