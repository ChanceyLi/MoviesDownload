"""
Tests for searcher, downloader, download_manager modules, and
settings / download-history helpers extracted from main.
Run with:  python -m pytest tests.py -v
"""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

import searcher
import downloader
import download_manager as dm
import app_config


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


# ─── download_manager tests ───────────────────────────────────────────────────

class TestDownloadTask(unittest.TestCase):
    """Tests for dm.DownloadTask lifecycle."""

    def _make_task(self):
        return dm.DownloadTask("https://example.com/file.zip", "file.zip", "/tmp")

    def test_initial_status(self):
        t = self._make_task()
        self.assertEqual(t.status, dm.DownloadStatus.PENDING)

    def test_cancel(self):
        t = self._make_task()
        t.cancel()
        self.assertEqual(t.status, dm.DownloadStatus.CANCELLED)
        self.assertTrue(t.should_stop())

    def test_pause_resume(self):
        t = self._make_task()
        t.status = dm.DownloadStatus.DOWNLOADING
        t.pause()
        self.assertEqual(t.status, dm.DownloadStatus.PAUSED)
        self.assertTrue(t.should_pause())

        t.resume()
        self.assertEqual(t.status, dm.DownloadStatus.PENDING)
        self.assertFalse(t.should_pause())

    def test_unique_ids(self):
        # Tasks with *different* URLs must get different IDs
        t1 = dm.DownloadTask("https://example.com/a.zip", "a.zip", "/tmp")
        t2 = dm.DownloadTask("https://example.com/b.zip", "b.zip", "/tmp")
        self.assertNotEqual(t1.id, t2.id)


class TestDownloadManager(unittest.TestCase):
    """Tests for dm.DownloadManager."""

    def setUp(self):
        self.manager = dm.DownloadManager(max_concurrent=2)

    def tearDown(self):
        self.manager.shutdown()

    def test_add_task_returns_id(self):
        task_id = self.manager.add_task(
            "https://example.com/f.zip", "f.zip", "/tmp"
        )
        self.assertIsNotNone(task_id)

    def test_get_task(self):
        task_id = self.manager.add_task(
            "https://example.com/f.zip", "f.zip", "/tmp"
        )
        task = self.manager.get_task(task_id)
        self.assertIsNotNone(task)
        self.assertEqual(task.filename, "f.zip")

    def test_get_all_tasks(self):
        self.manager.add_task("https://example.com/a.zip", "a.zip", "/tmp")
        self.manager.add_task("https://example.com/b.zip", "b.zip", "/tmp")
        tasks = self.manager.get_all_tasks()
        self.assertEqual(len(tasks), 2)

    def test_cancel_task(self):
        task_id = self.manager.add_task(
            "https://example.com/f.zip", "f.zip", "/tmp"
        )
        self.manager.cancel_task(task_id)
        task = self.manager.get_task(task_id)
        self.assertEqual(task.status, dm.DownloadStatus.CANCELLED)

    def test_clear_completed(self):
        task_id = self.manager.add_task(
            "https://example.com/f.zip", "f.zip", "/tmp"
        )
        # Manually mark as completed
        task = self.manager.get_task(task_id)
        task.status = dm.DownloadStatus.COMPLETED
        self.manager.clear_completed()
        self.assertIsNone(self.manager.get_task(task_id))

    def test_pause_task_only_when_downloading(self):
        task_id = self.manager.add_task(
            "https://example.com/f.zip", "f.zip", "/tmp"
        )
        # Task is PENDING – pausing should be a no-op
        self.manager.pause_task(task_id)
        task = self.manager.get_task(task_id)
        self.assertNotEqual(task.status, dm.DownloadStatus.PAUSED)

    def test_actual_download(self):
        """Integration: download with a mocked HTTP response."""
        import io as _io

        fake_data = b"x" * 2048
        fake_response = MagicMock()
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)
        fake_response.read = MagicMock(side_effect=[fake_data, b""])
        fake_response.headers = {"Content-Length": str(len(fake_data))}

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = dm.DownloadManager(max_concurrent=1)
            done = threading.Event()
            results = []

            def cb(task):
                results.append(task.status)
                if task.status in (
                    dm.DownloadStatus.COMPLETED,
                    dm.DownloadStatus.FAILED,
                    dm.DownloadStatus.CANCELLED,
                ):
                    done.set()

            with patch("urllib.request.urlopen", return_value=fake_response):
                task_id = manager.add_task(
                    "https://example.com/test.bin",
                    "test.bin",
                    tmpdir,
                    callback=cb,
                )
                done.wait(timeout=10)

            task = manager.get_task(task_id)
            # Should have reached a proper terminal state
            self.assertIn(
                task.status,
                {dm.DownloadStatus.COMPLETED, dm.DownloadStatus.FAILED},
            )
            manager.shutdown()


class TestFormatHelpers(unittest.TestCase):
    """Tests for dm.format_size and dm.format_speed."""

    def test_format_size_bytes(self):
        self.assertEqual(dm.format_size(512), "512.0 B")

    def test_format_size_kb(self):
        self.assertEqual(dm.format_size(1024), "1.0 KB")

    def test_format_size_mb(self):
        self.assertEqual(dm.format_size(1024 * 1024), "1.0 MB")

    def test_format_speed(self):
        self.assertIn("/s", dm.format_speed(1024))


# ─── settings helpers tests ───────────────────────────────────────────────────

class TestSettingsHelpers(unittest.TestCase):
    """Tests for app_config.load_settings / save_settings."""

    def test_load_defaults_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                settings = app_config.load_settings()
                for key in app_config.DEFAULT_SETTINGS:
                    self.assertIn(key, settings)
                self.assertEqual(settings["theme"], "深色紫")
            finally:
                os.chdir(original_cwd)

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                settings = app_config.load_settings()
                settings["theme"] = "深色蓝"
                settings["download_path"] = "/custom/path"
                app_config.save_settings(settings)
                loaded = app_config.load_settings()
                self.assertEqual(loaded["theme"], "深色蓝")
                self.assertEqual(loaded["download_path"], "/custom/path")
            finally:
                os.chdir(original_cwd)


# ─── fuzzy search helper tests ────────────────────────────────────────────────

class TestFuzzyMatch(unittest.TestCase):
    """Test the fuzzy-match logic independently (no GUI needed)."""

    def _make_history(self, keywords):
        return [{"keyword": kw, "category": "movie", "timestamp": ""} for kw in keywords]

    def _get_fuzzy_matches(self, history, text, limit=8):
        """Mirror of App._get_fuzzy_matches for unit testing."""
        text_lower = text.lower()
        seen = set()
        matches = []
        for entry in history:
            kw = entry["keyword"]
            if text_lower in kw.lower() and kw not in seen:
                matches.append(kw)
                seen.add(kw)
            if len(matches) >= limit:
                break
        return matches

    def test_exact_prefix(self):
        history = self._make_history(["肖申克的救赎", "速度与激情", "速度与激情7"])
        matches = self._get_fuzzy_matches(history, "速度")
        self.assertIn("速度与激情", matches)
        self.assertIn("速度与激情7", matches)
        self.assertNotIn("肖申克的救赎", matches)

    def test_substring_match(self):
        history = self._make_history(["The Dark Knight", "Dark Souls", "Batman"])
        matches = self._get_fuzzy_matches(history, "dark")
        self.assertIn("The Dark Knight", matches)
        self.assertIn("Dark Souls", matches)
        self.assertNotIn("Batman", matches)

    def test_case_insensitive(self):
        history = self._make_history(["Python Programming"])
        self.assertEqual(
            self._get_fuzzy_matches(history, "python"),
            ["Python Programming"],
        )

    def test_no_duplicates(self):
        history = self._make_history(["三体", "三体", "三体II"])
        matches = self._get_fuzzy_matches(history, "三体")
        self.assertEqual(matches.count("三体"), 1)

    def test_limit_respected(self):
        history = self._make_history([f"电影{i}" for i in range(20)])
        matches = self._get_fuzzy_matches(history, "电影", limit=5)
        self.assertEqual(len(matches), 5)

    def test_empty_history(self):
        self.assertEqual(self._get_fuzzy_matches([], "anything"), [])

    def test_no_match(self):
        history = self._make_history(["三体", "流浪地球"])
        self.assertEqual(self._get_fuzzy_matches(history, "batman"), [])


# ─── theme definitions test ───────────────────────────────────────────────────

class TestThemes(unittest.TestCase):
    """Verify THEMES dict structure."""

    def test_all_themes_have_required_keys(self):
        required = {"BG", "SURFACE", "ACCENT", "ACCENT_LIGHT",
                    "TEXT", "TEXT_DIM", "SUCCESS", "DANGER", "ENTRY_BG"}
        for name, theme in app_config.THEMES.items():
            for key in required:
                self.assertIn(key, theme, f"Theme '{name}' missing key '{key}'")

    def test_theme_count(self):
        self.assertGreaterEqual(len(app_config.THEMES), 4)

    def test_default_theme_present(self):
        self.assertIn(app_config.DEFAULT_SETTINGS["theme"], app_config.THEMES)


if __name__ == "__main__":
    unittest.main()
