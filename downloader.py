"""
Download link aggregation module.
Searches common Chinese resource sites for download links based on a title.
"""

import urllib.request
import urllib.parse
import re
import html

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

TIMEOUT = 10


def _fetch_page(url):
    """Fetch a page and return its HTML text, or None on error."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def get_download_links(title, subject_id=None, category="movie"):
    """
    Return a list of download link dicts for the given title/subject.

    Each dict contains:
        source  - name of the source site
        name    - human-readable link label
        url     - the download/resource URL
        magnet  - magnet URI if available (may be empty string)

    Searches multiple aggregator sites and returns combined results.
    """
    links = []

    # 1. BT-Rabbit (BT兔) – magnet/torrent search
    bt_links = _search_btrabbit(title)
    links.extend(bt_links)

    # 2. Douban resource comment page
    if subject_id:
        douban_links = _douban_resource_links(subject_id, category)
        links.extend(douban_links)

    # 3. Rarbg-like public index (1337x JSON API placeholder)
    if not links:
        links.append(
            {
                "source": "提示",
                "name": f'在磁力搜索引擎搜索 "{title}"',
                "url": "https://www.magnet.la/s/" + urllib.parse.quote(title),
                "magnet": "",
            }
        )

    return links


def _search_btrabbit(title):
    """Search BT-Rabbit for magnet links for the given title."""
    encoded = urllib.parse.quote(title)
    url = f"https://www.btrabbit.net/search?q={encoded}&type=movie"
    page = _fetch_page(url)
    if not page:
        return []

    results = []
    # Extract entries: title + magnet link
    for m in re.finditer(
        r'<a[^>]+href="(/detail/[^"]+)"[^>]*>(.*?)</a>.*?'
        r'(magnet:[^"&\s]+)',
        page,
        re.S,
    ):
        href = "https://www.btrabbit.net" + m.group(1)
        label = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        magnet = m.group(3)
        if label:
            results.append(
                {
                    "source": "BT兔",
                    "name": html.unescape(label),
                    "url": href,
                    "magnet": magnet,
                }
            )
        if len(results) >= 10:
            break

    return results


def _douban_resource_links(subject_id, category="movie"):
    """
    Look for resource comments (含资源链接) posted under a Douban subject.
    These are user-posted comments mentioning download resources.
    """
    if category == "movie":
        base = f"https://movie.douban.com/subject/{subject_id}/comments"
    elif category == "book":
        base = f"https://book.douban.com/subject/{subject_id}/reviews"
    else:
        return []

    page = _fetch_page(base + "?sort=new_score&status=P&percent_type=")
    if not page:
        return []

    results = []
    # Match HTTP(S) URLs in comment text
    for m in re.finditer(
        r'(https?://(?:pan\.baidu\.com|mega\.nz|drive\.google\.com|'
        r'aliyundrive\.com|www\.aliyundrive\.com|'
        r'www\.123pan\.com|quark\.cn|pan\.quark\.cn)'
        r'[^\s"<>]+)',
        page,
    ):
        link = m.group(1).rstrip(".,;)")
        source = _guess_source(link)
        if not any(r["url"] == link for r in results):
            results.append(
                {
                    "source": source,
                    "name": f"{source} 资源链接",
                    "url": link,
                    "magnet": "",
                }
            )
        if len(results) >= 8:
            break

    return results


def _guess_source(url):
    """Return a friendly name for a known cloud storage URL."""
    mapping = {
        "pan.baidu.com": "百度网盘",
        "mega.nz": "Mega",
        "drive.google.com": "Google Drive",
        "aliyundrive.com": "阿里云盘",
        "123pan.com": "123云盘",
        "quark.cn": "夸克网盘",
        "pan.quark.cn": "夸克网盘",
    }
    for domain, name in mapping.items():
        if domain in url:
            return name
    return "网络资源"
