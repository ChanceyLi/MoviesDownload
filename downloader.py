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

    # 3. Aggregated search links from multiple resource sites (reference.js)
    links.extend(_generate_site_links(title, category))

    # 4. Fallback when nothing else is found
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


def _generate_site_links(title, category="movie"):
    """
    Generate a list of search-link dicts for multiple resource sites aggregated
    from reference.js.  Each entry is a direct search URL the user can open in
    a browser; no HTTP requests are made here.

    Categories of sites mirrored from the reference.js site_map:
      - 公共磁力/BT搜索  (public BT / magnet search engines)
      - 影视资源网站      (movie/TV resource websites)
      - 在线正版视频      (licensed streaming platforms)
      - 云盘搜索          (cloud-drive resource search)
      - 图书资源          (book-specific, only when category == "book")
      - 音乐资源          (music-specific, only when category == "music")
    """
    q = urllib.parse.quote(title)
    links = []

    # ── 公共磁力/BT搜索 ────────────────────────────────────────────────────────
    if category in ("movie", "music"):
        bt_sites = [
            ("磁力搜索", "磁力搜索: " + title, "https://www.magnet.la/s/" + q),
            ("磁力猫", "磁力猫: " + title, "https://www.cilimao.cc/search/" + q),
            ("1337x", "1337x: " + title, "https://1337x.to/search/" + q + "/1/"),
            ("RARBG", "RARBG: " + title, "https://rargb.to/torrents.php?search=" + q),
            ("海盗湾", "海盗湾: " + title, "https://thepiratebay.org/search.php?q=" + q),
        ]
        for source, name, url in bt_sites:
            links.append({"source": source, "name": name, "url": url, "magnet": ""})

    # ── 影视资源网站 ───────────────────────────────────────────────────────────
    if category == "movie":
        resource_sites = [
            ("BD影视", "BD影视: " + title,
             "https://www.bd-film.cc/search.jspx?q=" + q),
            ("比特大雄", "比特大雄: " + title,
             "https://www.btdx8.com/?s=" + q),
            ("迅雷影天堂", "迅雷影天堂: " + title,
             "https://www.xl720.com/?s=" + q),
            ("片源网", "片源网: " + title,
             "http://pianyuan.org/search?q=" + q),
            ("音范丝", "音范丝: " + title,
             "http://www.yinfans.me/?s=" + q),
            ("中国高清网", "中国高清网: " + title,
             "http://gaoqing.la/?s=" + q),
        ]
        for source, name, url in resource_sites:
            links.append({"source": source, "name": name, "url": url, "magnet": ""})

    # ── 在线正版视频 ───────────────────────────────────────────────────────────
    if category in ("movie",):
        streaming_sites = [
            ("爱奇艺", "爱奇艺: " + title,
             "https://so.iqiyi.com/so/q_" + q),
            ("哔哩哔哩", "哔哩哔哩: " + title,
             "https://search.bilibili.com/all?keyword=" + q),
            ("腾讯视频", "腾讯视频: " + title,
             "https://v.qq.com/x/search/?q=" + q),
            ("优酷", "优酷: " + title,
             "https://www.soku.com/nt/search/q_" + q),
            ("芒果TV", "芒果TV: " + title,
             "https://so.mgtv.com/so/k-" + q),
        ]
        for source, name, url in streaming_sites:
            links.append({"source": source, "name": name, "url": url, "magnet": ""})

    # ── 云盘搜索 ───────────────────────────────────────────────────────────────
    cloud_sites = [
        ("阿里小站", "阿里小站: " + title,
         "https://pan666.net/?q=" + q),
        ("云盘资源网", "云盘资源网: " + title,
         "https://www.yunpanziyuan.com/fontsearch.htm?fontname=" + q),
        ("网盘小站", "网盘小站: " + title,
         "https://wpxz.org/?q=" + q),
        ("T-REX", "T-REX 网盘: " + title,
         "https://t-rex.tzfile.com/?s=" + q),
    ]
    for source, name, url in cloud_sites:
        links.append({"source": source, "name": name, "url": url, "magnet": ""})

    # ── 图书资源 ───────────────────────────────────────────────────────────────
    if category == "book":
        book_sites = [
            ("鸠摩搜书", "鸠摩搜书: " + title,
             "https://www.jiumodiary.com/?s=" + q),
            ("Z-Library", "Z-Library: " + title,
             "https://z-lib.org/s/" + q),
            ("书格", "书格: " + title,
             "https://new.shuge.org/?s=" + q),
            ("古登堡", "古登堡: " + title,
             "https://www.gutenberg.org/ebooks/search/?query=" + q),
        ]
        for source, name, url in book_sites:
            links.append({"source": source, "name": name, "url": url, "magnet": ""})

    # ── 音乐资源 ───────────────────────────────────────────────────────────────
    if category == "music":
        music_sites = [
            ("网易云音乐", "网易云: " + title,
             "https://music.163.com/#/search/m/?s=" + q),
            ("QQ音乐", "QQ音乐: " + title,
             "https://y.qq.com/portal/search.html#page=1&searchid=1&remoteplace=txt.yqq.top&s=" + q),
            ("酷我音乐", "酷我: " + title,
             "https://www.kuwo.cn/search/list?key=" + q),
            ("DicMusic", "DicMusic: " + title,
             "https://dicmusic.club/torrents.php?notnewword=1&searchstr=" + q),
        ]
        for source, name, url in music_sites:
            links.append({"source": source, "name": name, "url": url, "magnet": ""})

    return links
