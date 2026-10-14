using System.Net;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace PixivBatchBookmark.Core;

public static class SessionParser
{
    public static LoginSession Parse(string html)
    {
        foreach (Match meta in Regex.Matches(html, @"<meta\b[^>]*>", RegexOptions.IgnoreCase))
        {
            var attributes = Attributes(meta.Value);
            if (!attributes.TryGetValue("name", out var name) || name != "global-data" || !attributes.TryGetValue("content", out var content)) continue;
            try
            {
                using var doc = ParseJson(content);
                var root = doc.RootElement;
                if (!root.TryGetProperty("token", out var token) || !root.TryGetProperty("userData", out var user)) continue;
                if (ReadSession(user, token) is { } session) return session;
            }
            catch (Exception ex) when (ex is JsonException or InvalidOperationException or KeyNotFoundException) { }
        }
        // The current homepage uses Next.js data instead of legacy global-data.
        // Only userData.self identifies the signed-in user; users contains other artists.
        foreach (Match script in Regex.Matches(html, @"<script\b([^>]*)>(.*?)</script\s*>", RegexOptions.IgnoreCase | RegexOptions.Singleline))
        {
            var attributes = Attributes(script.Groups[1].Value);
            if (!attributes.TryGetValue("id", out var id) || id != "__NEXT_DATA__") continue;
            try
            {
                using var doc = ParseJson(script.Groups[2].Value);
                var page = doc.RootElement.GetProperty("props").GetProperty("pageProps");
                if (!page.TryGetProperty("isLoggedIn", out var loggedIn) || loggedIn.ValueKind != JsonValueKind.True) continue;
                using var state = ParseJson(page.GetProperty("serverSerializedPreloadedState").GetRawText());
                var user = state.RootElement.GetProperty("userData").GetProperty("self");
                var token = state.RootElement.GetProperty("api").GetProperty("token");
                if (ReadSession(user, token) is { } session) return session;
            }
            catch (Exception ex) when (ex is JsonException or InvalidOperationException or KeyNotFoundException) { }
        }
        throw new PixivException("未检测到有效登录身份和收藏安全令牌。请完成网页登录，再打开 Pixiv 首页重试；若持续失败，网站页面结构可能已变化。");
    }

    private static LoginSession? ReadSession(JsonElement user, JsonElement token)
    {
        if (user.ValueKind != JsonValueKind.Object || token.ValueKind != JsonValueKind.String || !user.TryGetProperty("id", out var identity)) return null;
        var id = identity.ToString();
        var csrf = token.GetString() ?? "";
        if (!long.TryParse(id, out var userId) || userId <= 0 || !Regex.IsMatch(csrf, @"^[A-Za-z0-9_-]{3,256}$")) return null;
        var name = user.TryGetProperty("name", out var username) && username.ValueKind == JsonValueKind.String ? username.GetString() ?? id : id;
        return new(id, name, csrf);
    }

    private static JsonDocument ParseJson(string text)
    {
        // Some page versions wrap global-data in a JSON string as well as HTML escaping.
        var doc = JsonDocument.Parse(text);
        if (doc.RootElement.ValueKind != JsonValueKind.String) return doc;
        var decoded = doc.RootElement.GetString()!;
        doc.Dispose();
        return JsonDocument.Parse(decoded);
    }

    public static BookmarkDetails ParseBookmarkDetails(string html)
    {
        string? tagText = null;
        var comment = "";
        foreach (Match input in Regex.Matches(html, @"<input\b[^>]*>", RegexOptions.IgnoreCase))
        {
            var attr = Attributes(input.Value);
            if (!attr.TryGetValue("name", out var name)) continue;
            if (name == "tag" && attr.TryGetValue("value", out var value)) tagText = value;
            if (name == "comment" && attr.TryGetValue("value", out var note)) comment = note;
        }
        if (tagText is null) throw new PixivException("无法读取原收藏标签，未取消原收藏。请检查登录状态或网站接口变化。");
        return new(tagText.Split(' ', StringSplitOptions.RemoveEmptyEntries), comment);
    }

    private static Dictionary<string, string> Attributes(string tag)
    {
        var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (Match match in Regex.Matches(tag, "([a-zA-Z][a-zA-Z0-9_-]*)\\s*=\\s*(?:\"([^\"]*)\"|'([^']*)'|([^\\s>]+))"))
            result[match.Groups[1].Value] = WebUtility.HtmlDecode(match.Groups[2].Success ? match.Groups[2].Value : match.Groups[3].Success ? match.Groups[3].Value : match.Groups[4].Value);
        return result;
    }
}
