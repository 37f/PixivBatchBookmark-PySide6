namespace PixivBatchBookmark.Core;

public enum BookmarkMode { Public, Private }
public enum BatchAction { Bookmark, Remove }
public enum ItemStatus { Success, Skipped, Failed }
public record BookmarkState(string? BookmarkId, BookmarkMode? Mode)
{
    public bool IsBookmarked => BookmarkId is not null;
    public static BookmarkState None { get; } = new(null, null);
}
public record BookmarkDetails(IReadOnlyList<string> Tags, string Comment = "");
public record ItemResult(ItemStatus Status, string Message, bool StopBatch = false);
public record LoginSession(string UserId, string UserName, string CsrfToken);
public record ParseResult(IReadOnlyList<string> Ids, int DuplicateCount, IReadOnlyList<string> IgnoredLines);

public class PixivException(string message, bool stopBatch = true) : Exception(message)
{
    public bool StopBatch { get; } = stopBatch;
}

public sealed class PixivAuthenticationException(string message) : PixivException(message);

public interface IPixivClient
{
    Task<BookmarkState> GetStateAsync(string id, CancellationToken cancellationToken);
    Task<BookmarkDetails> GetDetailsAsync(string id, CancellationToken cancellationToken);
    Task AddAsync(string id, BookmarkMode mode, BookmarkDetails details, CancellationToken cancellationToken);
    Task RemoveAsync(string bookmarkId, CancellationToken cancellationToken);
}
