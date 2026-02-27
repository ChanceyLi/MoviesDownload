"""
Tests for searcher and downloader modules.
Run with:  python -m pytest tests.py -v
"""

import unittest
from unittest.mock import patch, MagicMock

import searcher
import downloader


# ─── searcher tests ───────────────────────────────────────────────────────────

class TestSearchDouban(unittest.TestCase):
    """Tests for searcher.search_douban()"""

    def _fake_fetch(self, url, params=None):
        """Return a minimal fake Douban suggest response."""
        return [
            {
                "id": "1292052",
                "title": "肖申克的救赎",
                "year": "1994",
                "rating": "9.7",
                "img": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p480747492.jpg",
                "url": "https://movie.douban.com/subject/1292052/",
                "sub_title": "The Shawshank Redemption",
            }
        ]

    def test_search_movie_returns_list(self):
        with patch.object(searcher, "_fetch_json", side_effect=self._fake_fetch):
            results = searcher.search_douban("肖申克", "movie")
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 1)

    def test_result_fields(self):
        with patch.object(searcher, "_fetch_json", side_effect=self._fake_fetch):
            results = searcher.search_douban("肖申克", "movie")
        r = results[0]
        self.assertEqual(r["id"], "1292052")
        self.assertEqual(r["title"], "肖申克的救赎")
        self.assertEqual(r["year"], "1994")
        self.assertEqual(r["rating"], "9.7")
        self.assertEqual(r["category"], "movie")

    def test_empty_response(self):
        with patch.object(searcher, "_fetch_json", return_value=None):
            results = searcher.search_douban("不存在的资源xyz", "movie")
        self.assertEqual(results, [])

    def test_empty_list_response(self):
        with patch.object(searcher, "_fetch_json", return_value=[]):
            results = searcher.search_douban("xxx", "book")
        self.assertEqual(results, [])

    def test_category_book_url(self):
        """Ensure book category uses book URL."""
        called_urls = []

        def capture(url, params=None):
            called_urls.append(url)
            return []

        with patch.object(searcher, "_fetch_json", side_effect=capture):
            searcher.search_douban("三体", "book")

        self.assertIn("book.douban.com", called_urls[0])

    def test_category_music_url(self):
        called_urls = []

        def capture(url, params=None):
            called_urls.append(url)
            return []

        with patch.object(searcher, "_fetch_json", side_effect=capture):
            searcher.search_douban("周杰伦", "music")

        self.assertIn("music.douban.com", called_urls[0])

    def test_html_entities_decoded(self):
        fake = [
            {
                "id": "123",
                "title": "速度&amp;激情",
                "year": "2001",
                "rating": "7.5",
                "img": "",
                "url": "",
                "sub_title": "Fast &amp; Furious",
            }
        ]
        with patch.object(searcher, "_fetch_json", return_value=fake):
            results = searcher.search_douban("速度", "movie")
        self.assertEqual(results[0]["title"], "速度&激情")


# ─── downloader tests ─────────────────────────────────────────────────────────

class TestGetDownloadLinks(unittest.TestCase):
    """Tests for downloader.get_download_links()"""

    def test_returns_list(self):
        with patch.object(downloader, "_fetch_page", return_value=None):
            links = downloader.get_download_links("肖申克的救赎", "1292052", "movie")
        self.assertIsInstance(links, list)

    def test_fallback_link_present_when_no_results(self):
        """When no sources return results, a fallback search engine link is provided."""
        with patch.object(downloader, "_fetch_page", return_value=None):
            links = downloader.get_download_links("肖申克的救赎", None, "movie")
        self.assertTrue(len(links) >= 1)
        # Fallback entry should contain the title in the URL or name
        combined = " ".join(l["name"] + l["url"] for l in links)
        self.assertIn("肖申克的救赎", combined)

    def test_link_dict_structure(self):
        with patch.object(downloader, "_fetch_page", return_value=None):
            links = downloader.get_download_links("三体", None, "book")
        for link in links:
            self.assertIn("source", link)
            self.assertIn("name", link)
            self.assertIn("url", link)
            self.assertIn("magnet", link)

    def test_baidu_pan_detected(self):
        fake_page = (
            '<span class="short">很好的资源</span>'
            ' https://pan.baidu.com/s/1abc123 提取码:abcd'
        )
        with patch.object(downloader, "_fetch_page", return_value=fake_page):
            links = downloader.get_download_links("三体", "2567698", "book")
        sources = [l["source"] for l in links]
        self.assertIn("百度网盘", sources)

    def test_guess_source(self):
        self.assertEqual(downloader._guess_source("https://pan.baidu.com/s/abc"), "百度网盘")
        self.assertEqual(downloader._guess_source("https://mega.nz/file/xyz"), "Mega")
        self.assertEqual(downloader._guess_source("https://aliyundrive.com/s/xxx"), "阿里云盘")
        self.assertEqual(downloader._guess_source("https://pan.quark.cn/s/xxx"), "夸克网盘")
        self.assertEqual(downloader._guess_source("https://example.com/file"), "网络资源")


class TestGenerateSiteLinks(unittest.TestCase):
    """Tests for downloader._generate_site_links()"""

    def test_movie_includes_bt_sites(self):
        links = downloader._generate_site_links("肖申克的救赎", "movie")
        sources = [l["source"] for l in links]
        self.assertIn("磁力搜索", sources)
        self.assertIn("1337x", sources)
        self.assertIn("RARBG", sources)

    def test_movie_includes_resource_sites(self):
        links = downloader._generate_site_links("肖申克的救赎", "movie")
        sources = [l["source"] for l in links]
        self.assertIn("BD影视", sources)
        self.assertIn("比特大雄", sources)
        self.assertIn("迅雷影天堂", sources)

    def test_movie_includes_streaming_sites(self):
        links = downloader._generate_site_links("肖申克的救赎", "movie")
        sources = [l["source"] for l in links]
        self.assertIn("爱奇艺", sources)
        self.assertIn("哔哩哔哩", sources)
        self.assertIn("腾讯视频", sources)

    def test_movie_includes_cloud_sites(self):
        links = downloader._generate_site_links("肖申克的救赎", "movie")
        sources = [l["source"] for l in links]
        self.assertIn("阿里小站", sources)
        self.assertIn("云盘资源网", sources)

    def test_book_includes_book_sites(self):
        links = downloader._generate_site_links("三体", "book")
        sources = [l["source"] for l in links]
        self.assertIn("Z-Library", sources)
        self.assertIn("鸠摩搜书", sources)
        # BT/streaming sites should NOT appear for books
        self.assertNotIn("爱奇艺", sources)

    def test_music_includes_music_sites(self):
        links = downloader._generate_site_links("周杰伦", "music")
        sources = [l["source"] for l in links]
        self.assertIn("网易云音乐", sources)
        self.assertIn("QQ音乐", sources)

    def test_title_encoded_in_urls(self):
        links = downloader._generate_site_links("三体", "movie")
        for link in links:
            self.assertIn("source", link)
            self.assertIn("name", link)
            self.assertIn("url", link)
            self.assertIn("magnet", link)
            self.assertEqual(link["magnet"], "")
            # URL must be a string
            self.assertIsInstance(link["url"], str)
            self.assertTrue(link["url"].startswith("http"))

    def test_title_present_in_url_or_name(self):
        links = downloader._generate_site_links("三体", "movie")
        for link in links:
            combined = link["name"] + link["url"]
            self.assertTrue(
                "三体" in combined or "%E4%B8%89%E4%BD%93" in combined,
                f"Title not found in link: {link}"
            )

    def test_get_download_links_includes_site_links(self):
        """get_download_links aggregates site links even when page fetch fails."""
        with patch.object(downloader, "_fetch_page", return_value=None):
            links = downloader.get_download_links("肖申克的救赎", None, "movie")
        sources = [l["source"] for l in links]
        self.assertIn("磁力搜索", sources)
        self.assertIn("BD影视", sources)
        self.assertIn("爱奇艺", sources)


if __name__ == "__main__":
    unittest.main()
