using System.Globalization;
using System.Net;
using System.Text;
using System.Text.Json;

namespace PixivBatchBookmark.Core;

public sealed class PixivHttpClient(HttpClient http, LoginSession session) : IPixivClient
{
    public async Task<BookmarkState> GetStateAsync(string id, CancellationToken cancellationToken)
    {
        ValidateId(id);
        using var request = Request(HttpMethod.Get, $"ajax/illust/{id}?lang=zh", id);
        using var data = await SendJsonAsync(request, cancellationToken);
        try
        {
            var bookmark = data.RootElement.GetProperty("body").GetProperty("bookmarkData");
            if (bookmark.ValueKind == JsonValueKind.Null)
            {
                // Null is also returned to anonymous viewers. Require the same
                // signed-in identity before using it as proof of deletion.
                await VerifyIdentityAsync(cancellationToken);
                return BookmarkState.None;
            }
            var bookmarkId = bookmark.GetProperty("id").ToString();
            ValidateId(bookmarkId);
            return new(bookmarkId, bookmark.GetProperty("private").GetBoolean() ? BookmarkMode.Private : BookmarkMode.Public);
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException or ArgumentException)
        { throw new PixivException("收藏状态响应格式发生变化，已停止批次"); }
    }

    public async Task<BookmarkDetails> GetDetailsAsync(string id, CancellationToken cancellationToken)
    {
        ValidateId(id);
        // The edit page provides the user's actual bookmark tags, unlike artwork tags.
        using var request = Request(HttpMethod.Get, $"bookmark_add.php?type=illust&illust_id={id}", id);
        using var response = await http.SendAsync(request, cancellationToken);
        CheckStatus(response.StatusCode);
        CheckRedirect(response);
        return SessionParser.ParseBookmarkDetails(await response.Content.ReadAsStringAsync(cancellationToken));
    }

    public async Task AddAsync(string id, BookmarkMode mode, BookmarkDetails details, CancellationToken cancellationToken)
    {
        ValidateId(id);
        using var request = Request(HttpMethod.Post, "ajax/illusts/bookmarks/add", id);
        var payload = JsonSerializer.Serialize(new { illust_id = id, restrict = mode == BookmarkMode.Private ? 1 : 0, comment = details.Comment, tags = details.Tags });
        request.Content = new StringContent(payload, Encoding.UTF8, "application/json");
        using var response = await SendJsonAsync(request, cancellationToken);
    }

    public async Task RemoveAsync(string bookmarkId, CancellationToken cancellationToken)
    {
        ValidateId(bookmarkId);
        using var request = Request(HttpMethod.Post, "ajax/illusts/bookmarks/delete", null);
        request.Content = new FormUrlEncodedContent(new Dictionary<string, string> { ["bookmark_id"] = bookmarkId });
        using var response = await SendJsonAsync(request, cancellationToken);
    }

    private HttpRequestMessage Request(HttpMethod method, string path, string? artworkId)
    {
        var request = new HttpRequestMessage(method, new Uri(new Uri("https://www.pixiv.net/"), path));
        request.Headers.Referrer = new Uri(artworkId is null ? "https://www.pixiv.net/" : $"https://www.pixiv.net/artworks/{artworkId}");
        request.Headers.Accept.ParseAdd("application/json");
        if (method != HttpMethod.Get) request.Headers.Add("x-csrf-token", session.CsrfToken);
        request.Headers.CacheControl = new() { NoCache = true, NoStore = true };
        return request;
    }

    private async Task<JsonDocument> SendJsonAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        using var response = await http.SendAsync(request, cancellationToken);
        CheckStatus(response.StatusCode);
        CheckRedirect(response);
        JsonDocument data;
        try { data = JsonDocument.Parse(await response.Content.ReadAsStringAsync(cancellationToken)); }
        catch (JsonException) { throw new PixivException("Pixiv 未返回有效接口数据，可能需要完成验证或重新登录；已停止批次"); }
        var root = data.RootElement;
        if (root.ValueKind != JsonValueKind.Object || !root.TryGetProperty("error", out var error) || error.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
        { data.Dispose(); throw new PixivException("Pixiv 接口响应格式变化，已停止批次"); }
        if (error.GetBoolean())
        { data.Dispose(); throw new PixivException("Pixiv 拒绝了操作，请检查作品权限、登录状态和收藏安全令牌；已停止批次"); }
        return data;
    }

    private static void CheckRedirect(HttpResponseMessage response)
    {
        if ((int)response.StatusCode is >= 300 and < 400) throw new PixivAuthenticationException("登录已失效或需要网页验证，请重新登录");
    }

    private static void CheckStatus(HttpStatusCode status)
    {
        if (status == HttpStatusCode.TooManyRequests) throw new PixivException("Pixiv 请求频率受限（429），已停止批次；请等待一段时间后重试");
        if (status is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden) throw new PixivAuthenticationException($"Pixiv 拒绝访问（{(int)status}），请重新登录或完成网页验证");
        if (status == HttpStatusCode.NotFound) throw new PixivException("作品不存在或当前账号无法访问（404）", false);
        if ((int)status >= 400) throw new PixivException($"Pixiv 请求失败（{(int)status}），已停止批次");
    }

    private static void ValidateId(string id)
    {
        if (!long.TryParse(id, NumberStyles.None, CultureInfo.InvariantCulture, out var value) || value <= 0) throw new ArgumentException("无效的 Pixiv ID");
    }

    private async Task VerifyIdentityAsync(CancellationToken cancellationToken)
    {
        using var request = Request(HttpMethod.Get, "", null);
        using var response = await http.SendAsync(request, cancellationToken);
        CheckStatus(response.StatusCode);
        CheckRedirect(response);
        LoginSession identity;
        try { identity = SessionParser.Parse(await response.Content.ReadAsStringAsync(cancellationToken)); }
        catch (PixivException) { throw new PixivAuthenticationException("无法确认登录身份，不能将网页中的未收藏状态视为取消成功；请重新登录"); }
        if (identity.UserId != session.UserId) throw new PixivAuthenticationException("当前登录身份与任务账号不同，已停止批次");
    }
}
