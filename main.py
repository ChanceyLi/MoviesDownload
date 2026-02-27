"""
MoviesDownload – Windows desktop application for searching and downloading
movies, novels, and other media resources from Douban (豆瓣).

Entry point: run this file directly or build with PyInstaller.
"""

import io
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
import urllib.request
import urllib.parse
import webbrowser
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

import searcher
import downloader
import download_manager as dm
from app_config import (
    THEMES, DEFAULT_SETTINGS, SETTINGS_FILE, DOWNLOAD_HISTORY_FILE,
    load_settings as _load_settings, save_settings as _save_settings,
)

# ─── optional image support ───────────────────────────────────────────────────
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ─── category options ─────────────────────────────────────────────────────────
CATEGORIES = [("电影", "movie"), ("图书", "book"), ("音乐", "music")]


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        # ── settings & theme ─────────────────────────────────────────────────
        self._settings = _load_settings()
        theme_name = self._settings.get("theme", "深色紫")
        self._theme = THEMES.get(theme_name, THEMES["深色紫"])

        # Shortcuts to current theme colours
        self._c = self._theme  # convenience alias used in helpers

        self.title("MoviesDownload – 豆瓣资源下载助手")
        self.geometry("1020x720")
        self.minsize(800, 580)
        self.configure(bg=self._c["BG"])

        # ── state ─────────────────────────────────────────────────────────────
        self._results = []
        self._selected = None
        self._search_thread = None
        self._links_thread = None
        self._links_cache = {}
        self._history_file = "search_history.json"
        self._history = self._load_history()
        self._download_history = self._load_download_history()
        self._cover_cache = {}          # url -> PhotoImage (keep refs to avoid GC)
        self._cover_fetch_thread = None
        self._ac_popup = None           # autocomplete Toplevel

        # ── download manager ─────────────────────────────────────────────────
        self._dl_manager = dm.DownloadManager(
            max_concurrent=self._settings.get("max_concurrent_downloads", 3)
        )
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()

    # ─── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_toolbar()
        self._build_panes()
        self._build_status_bar()

    def _build_toolbar(self):
        c = self._c
        bar = tk.Frame(self, bg=c["SURFACE"], pady=8)
        bar.pack(fill="x", padx=0, pady=0)

        tk.Label(
            bar, text="🎬 MoviesDownload", bg=c["SURFACE"], fg=c["ACCENT_LIGHT"],
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left", padx=(16, 20))

        # ── toolbar buttons ────────────────────────────────────────────────
        def _tbtn(parent, text, cmd):
            return tk.Button(
                parent, text=text, command=cmd,
                bg=c["SURFACE"], fg=c["TEXT"],
                activebackground=c["ACCENT"], activeforeground="white",
                font=("Segoe UI", 9), relief="flat",
                padx=10, pady=3, cursor="hand2",
            )

        _tbtn(bar, "📜 搜索历史", self._show_history).pack(side="left", padx=2)
        _tbtn(bar, "⬇️ 下载管理", self._show_download_manager).pack(side="left", padx=2)
        _tbtn(bar, "📂 下载历史", self._show_download_history).pack(side="left", padx=2)
        _tbtn(bar, "⚙️ 设置", self._show_settings).pack(side="left", padx=2)

        # ── separator ─────────────────────────────────────────────────────
        tk.Frame(bar, bg=c["TEXT_DIM"], width=1).pack(side="left", fill="y", padx=10, pady=4)

        # ── category radio buttons ─────────────────────────────────────────
        self._cat_var = tk.StringVar(value="movie")
        for label, value in CATEGORIES:
            tk.Radiobutton(
                bar, text=label, variable=self._cat_var, value=value,
                bg=c["SURFACE"], fg=c["TEXT"], selectcolor=c["ACCENT"],
                activebackground=c["SURFACE"], activeforeground=c["TEXT_DIM"],
                font=("Segoe UI", 10),
            ).pack(side="left", padx=3)

        # ── search entry ───────────────────────────────────────────────────
        self._search_var = tk.StringVar()
        self._search_entry = tk.Entry(
            bar, textvariable=self._search_var, bg=c["ENTRY_BG"], fg=c["TEXT"],
            insertbackground=c["TEXT"], font=("Segoe UI", 11),
            relief="flat", width=30,
        )
        self._search_entry.pack(side="left", padx=(12, 6), ipady=5)
        self._search_entry.bind("<Return>", lambda _e: self._do_search())
        self._search_entry.bind("<Escape>", lambda _e: self._hide_autocomplete())
        self._search_entry.bind("<Down>", self._ac_focus_list)

        # Autocomplete: fire on every key release except navigation keys
        self._search_var.trace_add("write", lambda *_: self.after(50, self._update_autocomplete))

        self._search_btn = tk.Button(
            bar, text="🔍 搜索", command=self._do_search,
            bg=c["ACCENT"], fg="white", activebackground=c["ACCENT_LIGHT"],
            font=("Segoe UI", 10, "bold"), relief="flat",
            padx=16, pady=4, cursor="hand2",
        )
        self._search_btn.pack(side="left")

    def _build_panes(self):
        c = self._c
        paned = tk.PanedWindow(self, orient="horizontal", bg=c["BG"], sashwidth=5)
        paned.pack(fill="both", expand=True, padx=8, pady=(4, 0))

        # ── left: result list ────────────────────────────────────────────────
        left = tk.Frame(paned, bg=c["BG"])
        paned.add(left, minsize=260)

        tk.Label(
            left, text="搜索结果", bg=c["BG"], fg=c["TEXT_DIM"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=4)

        list_frame = tk.Frame(left, bg=c["SURFACE"])
        list_frame.pack(fill="both", expand=True, pady=(2, 0))

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", bg=c["SURFACE"])
        scrollbar.pack(side="right", fill="y")

        self._listbox = tk.Listbox(
            list_frame, bg=c["SURFACE"], fg=c["TEXT"],
            selectbackground=c["ACCENT"], selectforeground="white",
            activestyle="none", font=("Segoe UI", 10),
            relief="flat", yscrollcommand=scrollbar.set,
            cursor="hand2",
        )
        self._listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self._listbox.yview)
        self._listbox.bind("<<ListboxSelect>>", self._on_select)

        # ── right: detail + links (vertical split) ────────────────────────
        right = tk.Frame(paned, bg=c["BG"])
        paned.add(right, minsize=440)

        right_paned = tk.PanedWindow(right, orient="vertical", bg=c["BG"], sashwidth=5)
        right_paned.pack(fill="both", expand=True)

        # Detail pane
        detail_outer = tk.Frame(right_paned, bg=c["BG"])
        right_paned.add(detail_outer, minsize=160)

        tk.Label(
            detail_outer, text="详细信息", bg=c["BG"], fg=c["TEXT_DIM"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=4)

        detail_body = tk.Frame(detail_outer, bg=c["SURFACE"])
        detail_body.pack(fill="both", expand=True, pady=(2, 4))

        # Cover image label (left side of detail_body)
        self._cover_label = tk.Label(
            detail_body, bg=c["SURFACE"], relief="flat",
            text="", width=8,
        )
        self._cover_label.pack(side="left", padx=(8, 4), pady=8, anchor="n")

        # Text area (right side of detail_body)
        detail_scroll = tk.Scrollbar(detail_body, orient="vertical", bg=c["SURFACE"])
        detail_scroll.pack(side="right", fill="y")

        self._detail_text = tk.Text(
            detail_body, bg=c["SURFACE"], fg=c["TEXT"], font=("Segoe UI", 10),
            relief="flat", wrap="word",
            padx=8, pady=8, state="disabled",
            yscrollcommand=detail_scroll.set,
        )
        self._detail_text.pack(fill="both", expand=True)
        detail_scroll.config(command=self._detail_text.yview)

        # Rich-text tags for detail pane
        self._detail_text.tag_configure(
            "title", font=("Segoe UI", 12, "bold"), foreground=c["TEXT"]
        )
        self._detail_text.tag_configure(
            "label", foreground=c["TEXT_DIM"], font=("Segoe UI", 9)
        )
        self._detail_text.tag_configure(
            "value", foreground=c["TEXT"], font=("Segoe UI", 10)
        )
        self._detail_text.tag_configure(
            "summary", foreground=c["TEXT"], font=("Segoe UI", 10),
            lmargin1=8, lmargin2=8,
        )
        self._detail_text.tag_configure(
            "link_detail", foreground=c["ACCENT_LIGHT"], underline=True
        )

        # Links pane
        links_outer = tk.Frame(right_paned, bg=c["BG"])
        right_paned.add(links_outer, minsize=180)

        links_header = tk.Frame(links_outer, bg=c["BG"])
        links_header.pack(fill="x")

        tk.Label(
            links_header, text="下载链接", bg=c["BG"], fg=c["TEXT_DIM"],
            font=("Segoe UI", 9),
        ).pack(side="left", padx=4)

        links_frame = tk.Frame(links_outer, bg=c["SURFACE"])
        links_frame.pack(fill="both", expand=True, pady=(2, 0))

        links_scroll = tk.Scrollbar(links_frame, orient="vertical", bg=c["SURFACE"])
        links_scroll.pack(side="right", fill="y")

        self._links_text = tk.Text(
            links_frame, bg=c["SURFACE"], fg=c["TEXT"], font=("Segoe UI", 10),
            relief="flat", wrap="word",
            padx=10, pady=8, state="disabled",
            yscrollcommand=links_scroll.set, cursor="arrow",
        )
        self._links_text.pack(fill="both", expand=True)
        links_scroll.config(command=self._links_text.yview)

        # Tag styles for links pane
        self._links_text.tag_configure("source", foreground=c["TEXT_DIM"], font=("Segoe UI", 9))
        self._links_text.tag_configure("magnet", foreground=c["SUCCESS"], underline=True)
        self._links_text.tag_configure("bold", font=("Segoe UI", 10, "bold"), foreground=c["TEXT"])
        self._links_text.tag_configure("section", foreground=c["ACCENT_LIGHT"],
                                       font=("Segoe UI", 9, "bold"))

        self._link_urls = []

    def _build_status_bar(self):
        c = self._c
        self._status_var = tk.StringVar(value="就绪 – 请输入关键字并选择分类进行搜索")
        bar = tk.Label(
            self, textvariable=self._status_var, bg=c["SURFACE"], fg=c["TEXT_DIM"],
            font=("Segoe UI", 9), anchor="w", padx=10,
        )
        bar.pack(fill="x", side="bottom")

    # ─── fuzzy-search autocomplete ────────────────────────────────────────────

    def _get_fuzzy_matches(self, text):
        """Return history keywords that contain *text* as a substring (case-insensitive)."""
        text_lower = text.lower()
        seen = set()
        matches = []
        for entry in self._history:
            kw = entry["keyword"]
            if text_lower in kw.lower() and kw not in seen:
                matches.append(kw)
                seen.add(kw)
            if len(matches) >= 8:
                break
        return matches

    def _update_autocomplete(self):
        text = self._search_var.get()
        if len(text) < 1:
            self._hide_autocomplete()
            return
        matches = self._get_fuzzy_matches(text)
        if matches:
            self._show_autocomplete(matches)
        else:
            self._hide_autocomplete()

    def _show_autocomplete(self, matches):
        c = self._c
        entry = self._search_entry

        # Position popup below search entry
        x = entry.winfo_rootx()
        y = entry.winfo_rooty() + entry.winfo_height()
        width = entry.winfo_width()

        if self._ac_popup is None or not self._ac_popup.winfo_exists():
            self._ac_popup = tk.Toplevel(self)
            self._ac_popup.wm_overrideredirect(True)
            self._ac_popup.configure(bg=c["SURFACE"])

            self._ac_list = tk.Listbox(
                self._ac_popup, bg=c["SURFACE"], fg=c["TEXT"],
                selectbackground=c["ACCENT"], selectforeground="white",
                activestyle="none", font=("Segoe UI", 10),
                relief="flat", cursor="hand2",
                highlightthickness=1, highlightcolor=c["ACCENT"],
            )
            self._ac_list.pack(fill="both", expand=True)
            self._ac_list.bind("<<ListboxSelect>>", self._ac_on_select)
            self._ac_list.bind("<Return>", self._ac_on_select)
            self._ac_list.bind("<Escape>", lambda _e: self._hide_autocomplete())

        self._ac_popup.geometry(f"{width}x{min(len(matches), 8) * 24}+{x}+{y}")
        self._ac_list.delete(0, "end")
        for m in matches:
            self._ac_list.insert("end", m)
        self._ac_popup.lift()

    def _hide_autocomplete(self):
        if self._ac_popup and self._ac_popup.winfo_exists():
            self._ac_popup.destroy()
        self._ac_popup = None

    def _ac_on_select(self, _event=None):
        if not self._ac_list:
            return
        sel = self._ac_list.curselection()
        if sel:
            keyword = self._ac_list.get(sel[0])
            self._hide_autocomplete()
            self._search_var.set(keyword)
            self._search_entry.icursor("end")
            self._do_search()

    def _ac_focus_list(self, _event=None):
        """Move keyboard focus into the autocomplete list."""
        if self._ac_popup and self._ac_popup.winfo_exists() and self._ac_list:
            self._ac_list.focus_set()
            if self._ac_list.size() > 0:
                self._ac_list.selection_set(0)

    # ─── event handlers ───────────────────────────────────────────────────────

    def _do_search(self):
        self._hide_autocomplete()
        keyword = self._search_var.get().strip()
        if not keyword:
            messagebox.showwarning("提示", "请输入搜索关键字")
            return

        category = self._cat_var.get()
        self._save_to_history(keyword, category)

        self._search_btn.config(state="disabled")
        self._listbox.delete(0, "end")
        self._clear_detail()
        self._clear_links()
        self._results = []
        self._selected = None
        self._set_status(f'正在搜索 "{keyword}"…')

        def run():
            results = searcher.search_douban(keyword, category)
            self.after(0, lambda: self._on_search_done(results))

        self._search_thread = threading.Thread(target=run, daemon=True)
        self._search_thread.start()

    def _on_search_done(self, results):
        self._search_btn.config(state="normal")
        if not results:
            self._set_status("未找到相关结果，请尝试其他关键字")
            return

        self._results = results
        for item in results:
            year = f" ({item['year']})" if item.get("year") else ""
            rating = f" ★{item['rating']}" if item.get("rating") else ""
            self._listbox.insert("end", f"{item['title']}{year}{rating}")

        self._set_status(f"找到 {len(results)} 条结果，点击查看详情和下载链接")

    def _on_select(self, _event):
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        item = self._results[idx]
        self._selected = item

        self._show_detail(item)
        self._fetch_cover(item.get("cover", ""))

        cache_key = f"{item.get('id')}_{item.get('category', 'movie')}"
        if cache_key in self._links_cache:
            links = self._links_cache[cache_key]
            self._show_links(links, item)
            self._set_status(f"已显示 {len(links)} 个缓存的下载链接")
            return

        self._clear_links()
        self._set_status(f'正在获取 "{item["title"]}" 的下载链接…')

        def run():
            links = downloader.get_download_links(
                item["title"], item.get("id"), item.get("category", "movie")
            )
            self._links_cache[cache_key] = links
            self.after(0, lambda: self._on_links_done(links, item))

        self._links_thread = threading.Thread(target=run, daemon=True)
        self._links_thread.start()

    def _on_links_done(self, links, item):
        self._show_links(links, item)
        if links:
            self._set_status(f"找到 {len(links)} 个下载链接 – 点击链接打开或直接下载")
        else:
            self._set_status("未找到下载链接，请在豆瓣页面手动搜索")

    # ─── cover image ──────────────────────────────────────────────────────────

    def _fetch_cover(self, url):
        """Fetch cover image asynchronously and display it."""
        self._cover_label.config(image="", text="")
        if not url or not HAS_PIL:
            return
        if url in self._cover_cache:
            self._cover_label.config(image=self._cover_cache[url])
            return

        def run():
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = resp.read()
                img = Image.open(io.BytesIO(data))
                img.thumbnail((100, 140), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self._cover_cache[url] = photo
                self.after(0, lambda: self._display_cover(url))
            except Exception:
                pass

        self._cover_fetch_thread = threading.Thread(target=run, daemon=True)
        self._cover_fetch_thread.start()

    def _display_cover(self, url):
        if url in self._cover_cache:
            self._cover_label.config(image=self._cover_cache[url], text="")

    # ─── display helpers ──────────────────────────────────────────────────────

    def _clear_detail(self):
        self._detail_text.config(state="normal")
        self._detail_text.delete("1.0", "end")
        self._detail_text.config(state="disabled")
        self._cover_label.config(image="", text="")

    def _clear_links(self):
        self._links_text.config(state="normal")
        self._links_text.delete("1.0", "end")
        self._links_text.config(state="disabled")
        self._link_urls = []

    def _show_detail(self, item):
        c = self._c
        t = self._detail_text
        t.config(state="normal")
        t.delete("1.0", "end")

        title = item.get("title", "")
        year = item.get("year", "")
        rating = item.get("rating", "")
        summary = item.get("summary", "")
        url = item.get("url", "")
        category = item.get("category", "")
        cat_label = {"movie": "🎬 电影", "book": "📚 图书", "music": "🎵 音乐"}.get(category, "")

        t.insert("end", f"{title}\n", "title")

        def _field(label, value):
            if value:
                t.insert("end", f"{label}: ", "label")
                t.insert("end", f"{value}\n", "value")

        if year:
            _field("年份", year)
        if rating:
            _field("评分", f"★ {rating}")
        if cat_label:
            _field("类型", cat_label)

        if summary:
            t.insert("end", "\n简介\n", "label")
            t.insert("end", summary + "\n", "summary")

        if url:
            t.insert("end", "\n豆瓣链接: ", "label")
            tag = f"detail_url_{id(item)}"
            t.insert("end", url, tag)
            t.tag_configure(tag, foreground=c["ACCENT_LIGHT"], underline=True)
            t.tag_bind(tag, "<Button-1>", lambda _e, u=url: webbrowser.open(u))
            t.tag_bind(tag, "<Enter>", lambda _e: t.config(cursor="hand2"))
            t.tag_bind(tag, "<Leave>", lambda _e: t.config(cursor="arrow"))
            t.insert("end", "\n")

        t.config(state="disabled")

    def _show_links(self, links, item):
        c = self._c
        t = self._links_text
        t.config(state="normal")
        t.delete("1.0", "end")
        self._link_urls = []

        if not links:
            t.insert("end", "未找到下载链接。\n\n建议直接访问豆瓣资源页面查找。")
            t.config(state="disabled")
            return

        # Group links by source category for a cleaner display
        prev_section = None
        for i, link in enumerate(links):
            source = link.get("source", "")
            name = link.get("name", "")
            url = link.get("url", "")
            magnet = link.get("magnet", "")

            # Source badge
            t.insert("end", f"[{source}] ", "source")

            # Clickable URL label
            if url:
                url_tag = f"link_{i}"
                t.insert("end", name or url, url_tag)
                t.tag_configure(url_tag, foreground=c["ACCENT_LIGHT"], underline=True)
                t.tag_bind(url_tag, "<Button-1>", lambda _e, u=url: webbrowser.open(u))
                t.tag_bind(url_tag, "<Enter>", lambda _e: t.config(cursor="hand2"))
                t.tag_bind(url_tag, "<Leave>", lambda _e: t.config(cursor="arrow"))
            else:
                t.insert("end", name)

            # Inline download button using a Text window embed
            if url and not magnet:
                btn = tk.Button(
                    t, text="⬇", font=("Segoe UI", 8), relief="flat",
                    bg=c["ACCENT"], fg="white", cursor="hand2",
                    padx=3, pady=0,
                    command=lambda u=url, n=name or item.get("title", "download"): (
                        self._start_download(u, n)
                    ),
                )
                t.window_create("end", window=btn, padx=4)

            t.insert("end", "\n")

            # Magnet link
            if magnet:
                m_tag = f"magnet_{i}"
                t.insert("end", "  🧲 ", "source")
                t.insert("end", magnet[:72] + "…", m_tag)
                t.tag_configure(m_tag, foreground=c["SUCCESS"], underline=True)
                t.tag_bind(m_tag, "<Button-1>", lambda _e, u=magnet: webbrowser.open(u))
                t.tag_bind(m_tag, "<Enter>", lambda _e: t.config(cursor="hand2"))
                t.tag_bind(m_tag, "<Leave>", lambda _e: t.config(cursor="arrow"))
                t.insert("end", "\n")

            t.insert("end", "\n")

        t.config(state="disabled")

    def _set_status(self, msg):
        self._status_var.set(msg)

    # ─── actual download ──────────────────────────────────────────────────────

    def _start_download(self, url, suggested_name):
        """Prompt for save location and enqueue download."""
        save_dir = self._settings.get("download_path", os.path.expanduser("~/Downloads"))
        # Derive a sane default filename: prefer URL path basename, fall back to suggested_name
        url_basename = os.path.basename(urllib.parse.urlparse(url).path)
        filename = url_basename or suggested_name or "download"

        chosen_path = filedialog.asksaveasfilename(
            title="保存文件",
            initialdir=save_dir,
            initialfile=filename,
        )
        if not chosen_path:
            return

        save_path = os.path.dirname(chosen_path)
        actual_filename = os.path.basename(chosen_path)

        def on_progress(task):
            self.after(0, lambda: self._set_status(
                f"下载中: {actual_filename}  {dm.format_size(task.downloaded_size)}"
                f"/{dm.format_size(task.total_size) if task.total_size else '?'}"
                f"  {dm.format_speed(task.speed)}"
            ))
            if task.status == dm.DownloadStatus.COMPLETED:
                # Record in download history
                self._add_download_history(
                    title=suggested_name, url=url,
                    filename=task.filename, save_path=task.save_path,
                    status="completed",
                )
                self.after(0, lambda: self._set_status(
                    f"✅ 下载完成: {task.filename}"
                ))
                if self._settings.get("auto_open_after_download"):
                    self.after(0, lambda: self._open_file(task.full_path))
            elif task.status == dm.DownloadStatus.FAILED:
                self.after(0, lambda: self._set_status(
                    f"❌ 下载失败: {task.error_message}"
                ))

        self._dl_manager.add_task(url, actual_filename, save_path, callback=on_progress)
        self._set_status(f"已加入下载队列: {actual_filename}")

    def _open_file(self, path):
        """Open a file using the configured application or system default."""
        open_with = self._settings.get("open_with", "").strip()
        try:
            if open_with:
                subprocess.Popen([open_with, path])
            elif sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("打开文件失败", str(e))

    # ─── download history ─────────────────────────────────────────────────────

    def _load_download_history(self):
        if not os.path.exists(DOWNLOAD_HISTORY_FILE):
            return []
        try:
            with open(DOWNLOAD_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_download_history(self):
        try:
            with open(DOWNLOAD_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._download_history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _add_download_history(self, title, url, filename, save_path, status):
        entry = {
            "title": title,
            "url": url,
            "filename": filename,
            "save_path": save_path,
            "full_path": os.path.join(save_path, filename),
            "status": status,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._download_history.insert(0, entry)
        self._download_history = self._download_history[:200]
        self._save_download_history()

    def _show_download_history(self):
        """Show the download history window."""
        c = self._c
        win = tk.Toplevel(self)
        win.title("下载历史")
        win.geometry("720x480")
        win.configure(bg=c["BG"])
        win.transient(self)
        win.grab_set()

        tk.Label(
            win, text="📂 下载历史", bg=c["BG"], fg=c["TEXT"],
            font=("Segoe UI", 14, "bold"), pady=10,
        ).pack()

        list_frame = tk.Frame(win, bg=c["SURFACE"])
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        sb = tk.Scrollbar(list_frame, orient="vertical")
        sb.pack(side="right", fill="y")

        cols = ("文件名", "状态", "保存路径", "时间")
        tree = ttk.Treeview(list_frame, columns=cols, show="headings",
                            yscrollcommand=sb.set)
        for col in cols:
            tree.heading(col, text=col)
        tree.column("文件名", width=200)
        tree.column("状态", width=60)
        tree.column("保存路径", width=220)
        tree.column("时间", width=130)
        tree.pack(fill="both", expand=True)
        sb.config(command=tree.yview)

        def _refresh():
            for row in tree.get_children():
                tree.delete(row)
            for entry in self._download_history:
                tree.insert("", "end", values=(
                    entry.get("filename", ""),
                    entry.get("status", ""),
                    entry.get("save_path", ""),
                    entry.get("timestamp", ""),
                ))

        _refresh()

        btn_frame = tk.Frame(win, bg=c["BG"])
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        def _open_selected():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("提示", "请先选择一条记录", parent=win)
                return
            idx = tree.index(sel[0])
            if idx < len(self._download_history):
                path = self._download_history[idx]["full_path"]
                if os.path.exists(path):
                    self._open_file(path)
                else:
                    messagebox.showwarning("提示", f"文件不存在:\n{path}", parent=win)

        def _open_folder():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("提示", "请先选择一条记录", parent=win)
                return
            idx = tree.index(sel[0])
            if idx < len(self._download_history):
                folder = self._download_history[idx]["save_path"]
                if os.path.isdir(folder):
                    self._open_file(folder)
                else:
                    messagebox.showwarning("提示", f"文件夹不存在:\n{folder}", parent=win)

        def _clear():
            if messagebox.askyesno("确认", "清空所有下载历史？", parent=win):
                self._download_history = []
                self._save_download_history()
                _refresh()

        def _btn(parent, text, cmd, color=None):
            return tk.Button(
                parent, text=text, command=cmd,
                bg=color or c["SURFACE"], fg=c["TEXT"],
                activebackground=c["ACCENT"], activeforeground="white",
                font=("Segoe UI", 10), relief="flat",
                padx=14, pady=5, cursor="hand2",
            )

        _btn(btn_frame, "📂 打开文件", _open_selected, c["ACCENT"]).pack(side="left", padx=4)
        _btn(btn_frame, "🗂️ 打开所在文件夹", _open_folder).pack(side="left", padx=4)
        _btn(btn_frame, "🗑️ 清空历史", _clear, c["DANGER"]).pack(side="left", padx=4)
        _btn(btn_frame, "关闭", win.destroy).pack(side="right", padx=4)

        tree.bind("<Double-Button-1>", lambda _e: _open_selected())

    # ─── download manager window ──────────────────────────────────────────────

    def _show_download_manager(self):
        """Show active/queued downloads with progress bars."""
        c = self._c
        win = tk.Toplevel(self)
        win.title("下载管理器")
        win.geometry("680x420")
        win.configure(bg=c["BG"])
        win.transient(self)

        tk.Label(
            win, text="⬇️ 下载管理器", bg=c["BG"], fg=c["TEXT"],
            font=("Segoe UI", 13, "bold"), pady=8,
        ).pack()

        list_frame = tk.Frame(win, bg=c["SURFACE"])
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        sb = tk.Scrollbar(list_frame, orient="vertical")
        sb.pack(side="right", fill="y")

        cols = ("文件名", "进度", "速度", "状态")
        tree = ttk.Treeview(list_frame, columns=cols, show="headings",
                            yscrollcommand=sb.set)
        for col in cols:
            tree.heading(col, text=col)
        tree.column("文件名", width=220)
        tree.column("进度", width=80)
        tree.column("速度", width=100)
        tree.column("状态", width=90)
        tree.pack(fill="both", expand=True)
        sb.config(command=tree.yview)

        def _refresh():
            tasks = self._dl_manager.get_all_tasks()
            for row in tree.get_children():
                tree.delete(row)
            for task in tasks:
                prog = f"{task.progress:.1f}%"
                speed = dm.format_speed(task.speed) if task.speed > 0 else "-"
                status_map = {
                    dm.DownloadStatus.PENDING: "等待中",
                    dm.DownloadStatus.DOWNLOADING: "下载中",
                    dm.DownloadStatus.PAUSED: "已暂停",
                    dm.DownloadStatus.COMPLETED: "✅ 完成",
                    dm.DownloadStatus.FAILED: "❌ 失败",
                    dm.DownloadStatus.CANCELLED: "取消",
                }
                status_str = status_map.get(task.status, str(task.status))
                tree.insert("", "end", iid=task.id, values=(
                    task.filename, prog, speed, status_str
                ))
            win.after(1000, _refresh)

        _refresh()

        btn_frame = tk.Frame(win, bg=c["BG"])
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        def _pause():
            for sel in tree.selection():
                self._dl_manager.pause_task(sel)

        def _resume():
            for sel in tree.selection():
                self._dl_manager.resume_task(sel)

        def _cancel():
            for sel in tree.selection():
                self._dl_manager.cancel_task(sel)

        def _clear_done():
            self._dl_manager.clear_completed()

        def _btn(parent, text, cmd, color=None):
            return tk.Button(
                parent, text=text, command=cmd,
                bg=color or c["SURFACE"], fg=c["TEXT"],
                activebackground=c["ACCENT"], activeforeground="white",
                font=("Segoe UI", 10), relief="flat",
                padx=12, pady=5, cursor="hand2",
            )

        _btn(btn_frame, "⏸ 暂停", _pause).pack(side="left", padx=3)
        _btn(btn_frame, "▶ 继续", _resume).pack(side="left", padx=3)
        _btn(btn_frame, "✖ 取消", _cancel, c["DANGER"]).pack(side="left", padx=3)
        _btn(btn_frame, "清除已完成", _clear_done).pack(side="left", padx=3)
        _btn(btn_frame, "关闭", win.destroy).pack(side="right", padx=3)

    # ─── settings window ──────────────────────────────────────────────────────

    def _show_settings(self):
        c = self._c
        win = tk.Toplevel(self)
        win.title("设置")
        win.geometry("520x400")
        win.configure(bg=c["BG"])
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        tk.Label(
            win, text="⚙️ 设置", bg=c["BG"], fg=c["TEXT"],
            font=("Segoe UI", 14, "bold"), pady=10,
        ).pack()

        form = tk.Frame(win, bg=c["BG"])
        form.pack(fill="both", expand=True, padx=24)

        def _row(parent, label_text, row):
            tk.Label(
                parent, text=label_text, bg=c["BG"], fg=c["TEXT_DIM"],
                font=("Segoe UI", 10), anchor="w", width=18,
            ).grid(row=row, column=0, sticky="w", pady=6)

        # ── download path ────────────────────────────────────────────────
        _row(form, "默认下载路径:", 0)
        path_var = tk.StringVar(value=self._settings.get("download_path", ""))
        path_entry = tk.Entry(
            form, textvariable=path_var, bg=c["ENTRY_BG"], fg=c["TEXT"],
            insertbackground=c["TEXT"], font=("Segoe UI", 10), relief="flat",
            width=26,
        )
        path_entry.grid(row=0, column=1, padx=(0, 4))

        def browse():
            d = filedialog.askdirectory(title="选择下载文件夹", parent=win)
            if d:
                path_var.set(d)

        tk.Button(
            form, text="…", command=browse,
            bg=c["SURFACE"], fg=c["TEXT"], relief="flat",
            font=("Segoe UI", 10), padx=6, cursor="hand2",
        ).grid(row=0, column=2)

        # ── theme ─────────────────────────────────────────────────────────
        _row(form, "皮肤主题:", 1)
        theme_var = tk.StringVar(value=self._settings.get("theme", "深色紫"))
        theme_combo = ttk.Combobox(
            form, textvariable=theme_var,
            values=list(THEMES.keys()), state="readonly", width=18,
        )
        theme_combo.grid(row=1, column=1, sticky="w", pady=6)
        tk.Label(
            form, text="(重启后生效)", bg=c["BG"], fg=c["TEXT_DIM"],
            font=("Segoe UI", 8),
        ).grid(row=1, column=2, sticky="w", padx=4)

        # ── concurrent downloads ──────────────────────────────────────────
        _row(form, "最大并发下载:", 2)
        concur_var = tk.IntVar(value=self._settings.get("max_concurrent_downloads", 3))
        tk.Spinbox(
            form, from_=1, to=10, textvariable=concur_var,
            bg=c["ENTRY_BG"], fg=c["TEXT"], insertbackground=c["TEXT"],
            relief="flat", font=("Segoe UI", 10), width=6,
            buttonbackground=c["SURFACE"],
        ).grid(row=2, column=1, sticky="w", pady=6)

        # ── auto-open ─────────────────────────────────────────────────────
        _row(form, "下载完成后自动打开:", 3)
        auto_open_var = tk.BooleanVar(value=self._settings.get("auto_open_after_download", False))
        tk.Checkbutton(
            form, variable=auto_open_var,
            bg=c["BG"], activebackground=c["BG"],
            selectcolor=c["ACCENT"],
        ).grid(row=3, column=1, sticky="w")

        # ── open with ─────────────────────────────────────────────────────
        _row(form, "打开方式 (程序路径):", 4)
        openwith_var = tk.StringVar(value=self._settings.get("open_with", ""))
        tk.Entry(
            form, textvariable=openwith_var, bg=c["ENTRY_BG"], fg=c["TEXT"],
            insertbackground=c["TEXT"], font=("Segoe UI", 10), relief="flat",
            width=26,
        ).grid(row=4, column=1, pady=6)
        tk.Label(
            form, text="(留空=系统默认)", bg=c["BG"], fg=c["TEXT_DIM"],
            font=("Segoe UI", 8),
        ).grid(row=4, column=2, sticky="w", padx=4)

        # ── buttons ───────────────────────────────────────────────────────
        btn_frame = tk.Frame(win, bg=c["BG"])
        btn_frame.pack(fill="x", padx=24, pady=12)

        def _save():
            self._settings["download_path"] = path_var.get().strip()
            self._settings["theme"] = theme_var.get()
            self._settings["max_concurrent_downloads"] = concur_var.get()
            self._settings["auto_open_after_download"] = auto_open_var.get()
            self._settings["open_with"] = openwith_var.get().strip()
            _save_settings(self._settings)
            self._dl_manager.max_concurrent = concur_var.get()
            win.destroy()
            messagebox.showinfo("设置", "设置已保存。主题更改将在下次启动时生效。")

        tk.Button(
            btn_frame, text="保存", command=_save,
            bg=c["ACCENT"], fg="white", activebackground=c["ACCENT_LIGHT"],
            font=("Segoe UI", 10, "bold"), relief="flat",
            padx=20, pady=6, cursor="hand2",
        ).pack(side="left", padx=4)

        tk.Button(
            btn_frame, text="取消", command=win.destroy,
            bg=c["SURFACE"], fg=c["TEXT"], relief="flat",
            font=("Segoe UI", 10), padx=16, pady=6, cursor="hand2",
        ).pack(side="left", padx=4)

    # ─── search history ───────────────────────────────────────────────────────

    def _load_history(self):
        if not os.path.exists(self._history_file):
            return []
        try:
            with open(self._history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_to_history(self, keyword, category):
        entry = {
            "keyword": keyword,
            "category": category,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._history = [
            h for h in self._history
            if not (h["keyword"] == keyword and h["category"] == category)
        ]
        self._history.insert(0, entry)
        self._history = self._history[:50]
        try:
            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(self._history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _show_history(self):
        c = self._c
        if not self._history:
            messagebox.showinfo("历史记录", "暂无搜索历史")
            return

        win = tk.Toplevel(self)
        win.title("搜索历史")
        win.geometry("640x440")
        win.configure(bg=c["BG"])
        win.transient(self)
        win.grab_set()

        tk.Label(
            win, text="📜 搜索历史记录", bg=c["BG"], fg=c["TEXT"],
            font=("Segoe UI", 14, "bold"), pady=10,
        ).pack()

        list_frame = tk.Frame(win, bg=c["SURFACE"])
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        sb = tk.Scrollbar(list_frame, orient="vertical")
        sb.pack(side="right", fill="y")

        history_list = tk.Listbox(
            list_frame, bg=c["SURFACE"], fg=c["TEXT"],
            selectbackground=c["ACCENT"], selectforeground="white",
            activestyle="none", font=("Segoe UI", 10),
            relief="flat", yscrollcommand=sb.set, cursor="hand2",
        )
        history_list.pack(fill="both", expand=True)
        sb.config(command=history_list.yview)

        cat_labels = {"movie": "电影", "book": "图书", "music": "音乐"}
        for entry in self._history:
            cat = cat_labels.get(entry["category"], entry["category"])
            history_list.insert(
                "end", f"{entry['keyword']}  [{cat}]  {entry['timestamp']}"
            )

        btn_frame = tk.Frame(win, bg=c["BG"])
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        def _search_again():
            sel = history_list.curselection()
            if not sel:
                messagebox.showwarning("提示", "请选择一条历史记录", parent=win)
                return
            entry = self._history[sel[0]]
            win.destroy()
            self._search_var.set(entry["keyword"])
            self._cat_var.set(entry["category"])
            self._do_search()

        def _clear():
            if messagebox.askyesno("确认", "清空所有搜索历史？", parent=win):
                self._history = []
                try:
                    if os.path.exists(self._history_file):
                        os.remove(self._history_file)
                except Exception:
                    pass
                win.destroy()

        def _btn(parent, text, cmd, color=None):
            return tk.Button(
                parent, text=text, command=cmd,
                bg=color or c["SURFACE"], fg=c["TEXT"],
                activebackground=c["ACCENT"], activeforeground="white",
                font=("Segoe UI", 10), relief="flat",
                padx=14, pady=6, cursor="hand2",
            )

        _btn(btn_frame, "🔍 再次搜索", _search_again, c["ACCENT"]).pack(side="left", padx=4)
        _btn(btn_frame, "🗑️ 清空历史", _clear, c["DANGER"]).pack(side="left", padx=4)
        _btn(btn_frame, "关闭", win.destroy).pack(side="right", padx=4)

        history_list.bind("<Double-Button-1>", lambda _e: _search_again())

    # ─── lifecycle ────────────────────────────────────────────────────────────

    def _on_close(self):
        self._dl_manager.shutdown()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
