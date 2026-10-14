using System.Globalization;
using System.Text.RegularExpressions;

namespace PixivBatchBookmark.Core;

public static class IdParser
{
    private static readonly Regex Url = new(@"https?://[^\s<>""']+|\b(?:www\.)?pixiv\.net/[^\s<>""']+", RegexOptions.IgnoreCase);
    private static readonly Regex Label = new(@"\bpixiv\s*(?:id)?\s*[:：=]?\s*([0-9]+)\b|\bpid\s*[:：=]\s*([0-9]+)\b", RegexOptions.IgnoreCase);
    private static readonly Regex PlainList = new(@"^\s*[0-9]+(?:[\s,，;；、]+[0-9]+)*\s*$");

    public static ParseResult Parse(string text)
    {
        var ids = new List<string>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var ignored = new List<string>();
        var duplicateCount = 0;
        foreach (var line in text.Replace("\r", "").Split('\n'))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            var candidates = new List<(int Position, string Value)>();
            var remaining = line.ToCharArray();
            foreach (Match match in Url.Matches(line))
            {
                var value = match.Value.TrimEnd('.', ',', '，', '。', ')', '）', ']', '》', ';', '；');
                if (!value.StartsWith("http", StringComparison.OrdinalIgnoreCase)) value = "https://" + value;
                if (Uri.TryCreate(value, UriKind.Absolute, out var uri) &&
                    (uri.Host.Equals("pixiv.net", StringComparison.OrdinalIgnoreCase) || uri.Host.Equals("www.pixiv.net", StringComparison.OrdinalIgnoreCase)))
                {
                    var artwork = Regex.Match(uri.AbsolutePath, @"^/(?:[a-z]{2}(?:-[a-z]{2})?/)?artworks/([0-9]+)/?$", RegexOptions.IgnoreCase);
                    if (artwork.Success) candidates.Add((match.Index, artwork.Groups[1].Value));
                    else if (uri.AbsolutePath.Equals("/member_illust.php", StringComparison.OrdinalIgnoreCase))
                    {
                        var old = Regex.Match(uri.Query, @"(?:\?|&)illust_id=([0-9]+)(?:&|$)");
                        if (old.Success) candidates.Add((match.Index, old.Groups[1].Value));
                    }
                }
                // Never interpret user IDs or query parameters left inside URLs as artwork IDs.
                Array.Fill(remaining, ' ', match.Index, match.Length);
            }
            var rest = new string(remaining);
            foreach (Match match in Label.Matches(rest))
                candidates.Add((match.Index, match.Groups[1].Success ? match.Groups[1].Value : match.Groups[2].Value));
            // A numeric prefix beside a link is usually a list number, not another ID.
            if (PlainList.IsMatch(line))
                foreach (Match match in Regex.Matches(rest, @"[0-9]+")) candidates.Add((match.Index, match.Value));
            var accepted = false;
            foreach (var candidate in candidates.OrderBy(x => x.Position))
            {
                if (!long.TryParse(candidate.Value, NumberStyles.None, CultureInfo.InvariantCulture, out var number) || number <= 0) continue;
                accepted = true;
                var id = number.ToString(CultureInfo.InvariantCulture);
                if (seen.Add(id)) ids.Add(id); else duplicateCount++;
            }
            if (!accepted) ignored.Add(line);
        }
        return new(ids, duplicateCount, ignored);
    }
}
