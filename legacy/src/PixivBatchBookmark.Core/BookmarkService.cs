namespace PixivBatchBookmark.Core;

public sealed class BookmarkService(IPixivClient client)
{
    public async Task<ItemResult> ProcessAsync(string id, BatchAction action, BookmarkMode mode,
        CancellationToken cancellationToken, Action<string>? log = null)
    {
        cancellationToken.ThrowIfCancellationRequested();
        // A stop request takes effect between items. In particular it cannot interrupt
        // the remove/add pair and accidentally leave a converted artwork unbookmarked.
        var operationToken = CancellationToken.None;
        BookmarkState original;
        try { original = await client.GetStateAsync(id, operationToken); }
        catch (Exception ex) { return Failure(ex); }
        if (action == BatchAction.Remove && !original.IsBookmarked)
            return new(ItemStatus.Skipped, "未收藏，已跳过");
        if (action == BatchAction.Bookmark && original.IsBookmarked && original.Mode == mode)
            return new(ItemStatus.Skipped, $"已是{ModeName(mode)}收藏，已跳过");

        BookmarkDetails details = new([]);
        if (action == BatchAction.Bookmark && original.IsBookmarked)
        {
            try { details = await client.GetDetailsAsync(id, operationToken); }
            catch (Exception ex) { return Failure(ex); } // No deletion before metadata is saved.
        }
        try
        {
            if (original.IsBookmarked)
            {
                log?.Invoke(action == BatchAction.Remove ? "取消现有收藏" : $"将{ModeName(original.Mode!.Value)}切换为{ModeName(mode)}：先取消原收藏");
                await client.RemoveAsync(original.BookmarkId!, operationToken);
                if ((await client.GetStateAsync(id, operationToken)).IsBookmarked)
                    return new(ItemStatus.Failed, "取消后仍检测到收藏，已停止批次；请检查 Pixiv 页面", true);
            }
            if (action == BatchAction.Remove) return new(ItemStatus.Success, "已取消收藏并核验");
            log?.Invoke($"添加{ModeName(mode)}收藏");
            await client.AddAsync(id, mode, details, operationToken);
            var current = await client.GetStateAsync(id, operationToken);
            if (current.IsBookmarked && current.Mode == mode)
                return new(ItemStatus.Success, $"已{ModeName(mode)}收藏并核验");
            throw new PixivException("提交后未核验到目标收藏状态");
        }
        catch (Exception ex)
        {
            // Anonymous artwork reads can also return bookmarkData:null. A failed
            // authentication must never be relabeled as a successful deletion.
            if (ex is PixivAuthenticationException)
                return new(ItemStatus.Failed, ex.Message + "；操作后的收藏状态未确认，请重新登录并检查此作品", true);
            // Do not repeat a timed-out mutation blindly: the server may have applied it.
            BookmarkState actual;
            try { actual = await client.GetStateAsync(id, operationToken); }
            catch { return new(ItemStatus.Failed, "操作后的真实状态无法确认，已停止批次；请检查此作品", true); }
            if (action == BatchAction.Remove)
                return !actual.IsBookmarked ? new(ItemStatus.Success, "响应异常，但已核验取消成功", MustStop(ex)) : Failure(ex);
            if (actual.IsBookmarked && actual.Mode == mode)
                return new(ItemStatus.Success, $"响应异常，但已核验{ModeName(mode)}收藏成功", MustStop(ex));
            if (original.IsBookmarked && !actual.IsBookmarked)
            {
                log?.Invoke("转换未完成，尝试恢复原收藏和标签");
                try
                {
                    await client.AddAsync(id, original.Mode!.Value, details, operationToken);
                }
                catch { /* A lost response still requires read-back verification. */ }
                try
                {
                    var restored = await client.GetStateAsync(id, operationToken);
                    if (restored.IsBookmarked && restored.Mode == original.Mode)
                        return new(ItemStatus.Failed, $"转换失败，已恢复原{ModeName(original.Mode!.Value)}收藏；请稍后重试", true);
                }
                catch { /* State is unknown; stop and make the artwork ID visible in the UI. */ }
                return new(ItemStatus.Failed, "转换失败且无法核验原收藏恢复；已停止批次，请手动检查此作品", true);
            }
            return new(ItemStatus.Failed, SafeMessage(ex) + "；已停止批次，请检查此作品", true);
        }
    }

    private static bool MustStop(Exception ex) => ex is not PixivException p || p.StopBatch;
    private static ItemResult Failure(Exception ex) => new(ItemStatus.Failed, SafeMessage(ex), MustStop(ex));
    private static string SafeMessage(Exception ex) => ex is PixivException ? ex.Message : ex is TaskCanceledException ? "请求超时，请检查网络后重试" : "网络请求失败，请检查网络与登录状态";
    public static string ModeName(BookmarkMode mode) => mode == BookmarkMode.Public ? "公开" : "私密";
}
