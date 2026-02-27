"""
Douban (豆瓣) search module for movies, books, and music resources.
Uses Douban's public search API to fetch resource details.
"""

import urllib.request
import urllib.parse
import json
import re
import html


DOUBAN_SEARCH_URL = "https://www.douban.com/j/search"
DOUBAN_MOVIE_URL = "https://movie.douban.com/j/subject_suggest"
DOUBAN_BOOK_URL = "https://book.douban.com/j/subject_suggest"
DOUBAN_MUSIC_URL = "https://music.douban.com/j/subject_suggest"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.douban.com/",
}

TIMEOUT = 10


def _fetch_json(url, params=None):
    """Fetch URL and parse response as JSON. Returns parsed data or None."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def search_douban(keyword, category="movie"):
    """
    Search Douban for the given keyword.

    Args:
        keyword: Search keyword string
        category: One of 'movie', 'book', 'music'

    Returns:
        List of result dicts with keys: id, title, year, rating, cover, url, summary
    """
    if category == "movie":
        url = DOUBAN_MOVIE_URL
    elif category == "book":
        url = DOUBAN_BOOK_URL
    elif category == "music":
        url = DOUBAN_MUSIC_URL
    else:
        url = DOUBAN_MOVIE_URL

    data = _fetch_json(url, {"q": keyword})
    if not data:
        return []

    results = []
    for item in data:
        entry = {
            "id": item.get("id", ""),
            "title": html.unescape(item.get("title", "")),
            "year": item.get("year", ""),
            "rating": item.get("rating", ""),
            "cover": item.get("img", item.get("cover_url", "")),
            "url": item.get("url", ""),
            "summary": html.unescape(item.get("sub_title", "")),
            "category": category,
        }
        results.append(entry)

    return results


def get_resource_details(subject_id, category="movie"):
    """
    Fetch detailed info for a specific Douban subject.

    Returns a dict with detailed information or None on failure.
    """
    if category == "movie":
        api_url = f"https://movie.douban.com/subject/{subject_id}/"
    elif category == "book":
        api_url = f"https://book.douban.com/subject/{subject_id}/"
    elif category == "music":
        api_url = f"https://music.douban.com/subject/{subject_id}/"
    else:
        return None

    req = urllib.request.Request(api_url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            page = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None

    details = {"url": api_url, "id": subject_id, "category": category}

    title_m = re.search(r'<span property="v:itemreviewed"[^>]*>([^<]+)</span>', page)
    if title_m:
        details["title"] = html.unescape(title_m.group(1).strip())

    rating_m = re.search(
        r'<strong[^>]*class="ll rating_num"[^>]*property="v:average"[^>]*>([^<]+)</strong>',
        page,
    )
    if rating_m:
        details["rating"] = rating_m.group(1).strip()

    summary_m = re.search(
        r'property="v:summary"[^>]*>([\s\S]*?)</span>', page
    )
    if summary_m:
        raw = summary_m.group(1)
        raw = re.sub(r"<[^>]+>", "", raw)
        details["summary"] = html.unescape(raw.strip())

    return details
