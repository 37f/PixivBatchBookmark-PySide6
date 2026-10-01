"""Extract artwork IDs without mistaking dates, authors, or novel URLs for works."""

import re
import unicodedata
from urllib.parse import parse_qs, urlparse

URL_RE = re.compile(r"https?://[^\s<>\"']+|(?:www\.)?pixiv\.net/[^\s<>\"']+", re.I)
LABEL_RE = re.compile(r'(?<![A-Za-z])(?:pixiv\s*(?:id)?|作品\s*(?:id|编号)|id)\s*[:=#]\s*([0-9]{1,12})(?![0-9])', re.I)
LIST_RE = re.compile(r'\s*[0-9]+(?:[\s,;、|]+[0-9]+)*\s*')


def parse_ids(text: str) -> list[str]:
    text = unicodedata.normalize('NFKC', text)
    found = []
    seen = set()
    for line in text.splitlines():
        candidates = []
        masked = list(line)
        for match in URL_RE.finditer(line):
            url = match.group().rstrip('.,;，。;)）]')
            parsed = urlparse(url if '://' in url else 'https://' + url)
            if parsed.hostname in ('pixiv.net', 'www.pixiv.net'):
                artwork = re.fullmatch(r'/(?:[a-z]{2}/)?artworks/([0-9]{1,12})/?', parsed.path)
                if artwork:
                    candidates.append((match.start(), artwork.group(1)))
                elif parsed.path == '/member_illust.php':
                    value = parse_qs(parsed.query).get('illust_id', [''])[0]
                    if re.fullmatch(r'[0-9]{1,12}', value):
                        candidates.append((match.start(), value))
            masked[match.start():match.end()] = ' ' * (match.end() - match.start())
        remainder = ''.join(masked)
        candidates.extend((m.start(), m.group(1)) for m in LABEL_RE.finditer(remainder))
        # Only all-numeric lines are accepted as unlabelled lists.
        if LIST_RE.fullmatch(remainder):
            candidates.extend((m.start(), m.group()) for m in re.finditer(r'[0-9]+', remainder))
        for _, value in sorted(candidates):
            if len(value) <= 12 and int(value) > 0:
                value = str(int(value))
                if value not in seen:
                    seen.add(value)
                    found.append(value)
    return found
