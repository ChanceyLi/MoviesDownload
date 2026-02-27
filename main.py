"""
MoviesDownload – Windows desktop application for searching and downloading
movies, novels, and other media resources from Douban (豆瓣).

Entry point: run this file directly or build with PyInstaller.
"""

import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk, scrolledtext
import webbrowser
import json
import os
from datetime import datetime

import searcher
import downloader

# ─── color palette ───────────────────────────────────────────────────────────
BG = "#1e1e2e"
SURFACE = "#2a2a3e"
ACCENT = "#7c3aed"
ACCENT_LIGHT = "#a78bfa"
TEXT = "#e2e8f0"
TEXT_DIM = "#94a3b8"
SUCCESS = "#22c55e"
DANGER = "#ef4444"
ENTRY_BG = "#12121e"

# ─── category options ─────────────────────────────────────────────────────────
CATEGORIES = [("电影", "movie"), ("图书", "book"), ("音乐", "music")]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MoviesDownload – 豆瓣资源下载助手")
        self.geometry("900x680")
        self.minsize(750, 550)
        self.configure(bg=BG)

        self._results = []          # current search results
        self._selected = None       # currently selected result dict
        self._search_thread = None
        self._links_thread = None
        self._links_cache = {}      # cache: item_id -> links list
        self._history_file = "search_history.json"
        self._history = self._load_history()

        self._build_ui()

    # ─── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_search_bar()
        self._build_panes()
        self._build_status_bar()

    def _build_search_bar(self):
        bar = tk.Frame(self, bg=SURFACE, pady=8)
        bar.pack(fill="x", padx=0, pady=0)

        tk.Label(
            bar, text="🎬 MoviesDownload", bg=SURFACE, fg=ACCENT_LIGHT,
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left", padx=(16, 24))

        # History button
        tk.Button(
            bar, text="📜 历史", command=self._show_history,
            bg=SURFACE, fg=TEXT, activebackground=ACCENT,
            font=("Segoe UI", 9), relief="flat",
            padx=12, pady=2, cursor="hand2",
        ).pack(side="left", padx=(0, 8))

        # Category radio buttons
        self._cat_var = tk.StringVar(value="movie")
        for label, value in CATEGORIES:
            tk.Radiobutton(
                bar, text=label, variable=self._cat_var, value=value,
                bg=SURFACE, fg=TEXT, selectcolor=ACCENT,
                activebackground=SURFACE, activeforeground=TEXT_DIM,
                font=("Segoe UI", 10),
            ).pack(side="left", padx=4)

        # Search entry + button
        self._search_var = tk.StringVar()
        entry = tk.Entry(
            bar, textvariable=self._search_var, bg=ENTRY_BG, fg=TEXT,
            insertbackground=TEXT, font=("Segoe UI", 11),
            relief="flat", width=32,
        )
        entry.pack(side="left", padx=(16, 8), ipady=5)
        entry.bind("<Return>", lambda _e: self._do_search())

        self._search_btn = tk.Button(
            bar, text="搜索", command=self._do_search,
            bg=ACCENT, fg="white", activebackground=ACCENT_LIGHT,
            font=("Segoe UI", 10, "bold"), relief="flat",
            padx=18, pady=4, cursor="hand2",
        )
        self._search_btn.pack(side="left")

    def _build_panes(self):
        paned = tk.PanedWindow(self, orient="horizontal", bg=BG, sashwidth=5)
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        # ── left: result list ────────────────────────────────────────────────
        left = tk.Frame(paned, bg=BG)
        paned.add(left, minsize=260)

        tk.Label(
            left, text="搜索结果", bg=BG, fg=TEXT_DIM,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=4)

        list_frame = tk.Frame(left, bg=SURFACE)
        list_frame.pack(fill="both", expand=True, pady=(2, 0))

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", bg=SURFACE)
        scrollbar.pack(side="right", fill="y")

        self._listbox = tk.Listbox(
            list_frame, bg=SURFACE, fg=TEXT,
            selectbackground=ACCENT, selectforeground="white",
            activestyle="none", font=("Segoe UI", 10),
            relief="flat", yscrollcommand=scrollbar.set,
            cursor="hand2",
        )
        self._listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self._listbox.yview)
        self._listbox.bind("<<ListboxSelect>>", self._on_select)

        # ── right: detail + links ────────────────────────────────────────────
        right = tk.Frame(paned, bg=BG)
        paned.add(right, minsize=420)

        # Detail area
        detail_label = tk.Label(
            right, text="详细信息", bg=BG, fg=TEXT_DIM,
            font=("Segoe UI", 9),
        )
        detail_label.pack(anchor="w", padx=4)

        self._detail_text = tk.Text(
            right, bg=SURFACE, fg=TEXT, font=("Segoe UI", 10),
            relief="flat", wrap="word", height=10,
            padx=10, pady=8, state="disabled",
        )
        self._detail_text.pack(fill="x", padx=0, pady=(2, 6))

        # Links area
        tk.Label(
            right, text="下载链接", bg=BG, fg=TEXT_DIM,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=4)

        links_frame = tk.Frame(right, bg=SURFACE)
        links_frame.pack(fill="both", expand=True, pady=(2, 0))

        links_scroll = tk.Scrollbar(links_frame, orient="vertical", bg=SURFACE)
        links_scroll.pack(side="right", fill="y")

        self._links_text = tk.Text(
            links_frame, bg=SURFACE, fg=TEXT, font=("Segoe UI", 10),
            relief="flat", wrap="word",
            padx=10, pady=8, state="disabled",
            yscrollcommand=links_scroll.set, cursor="arrow",
        )
        self._links_text.pack(fill="both", expand=True)
        links_scroll.config(command=self._links_text.yview)

        # Configure hyperlink tag
        self._links_text.tag_configure(
            "link", foreground=ACCENT_LIGHT, underline=True
        )
        self._links_text.tag_configure("magnet", foreground=SUCCESS, underline=True)
        self._links_text.tag_configure("source", foreground=TEXT_DIM)
        self._links_text.tag_configure("bold", font=("Segoe UI", 10, "bold"), foreground=TEXT)

        self._link_urls = []  # list of (tag_name, url) for click handlers

    def _build_status_bar(self):
        self._status_var = tk.StringVar(value="就绪 – 请输入关键字并选择分类进行搜索")
        bar = tk.Label(
            self, textvariable=self._status_var, bg=SURFACE, fg=TEXT_DIM,
            font=("Segoe UI", 9), anchor="w", padx=10,
        )
        bar.pack(fill="x", side="bottom")

    # ─── event handlers ───────────────────────────────────────────────────────

    def _do_search(self):
        keyword = self._search_var.get().strip()
        if not keyword:
            messagebox.showwarning("提示", "请输入搜索关键字")
            return

        # Save to history
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
        
        # Check cache first
        cache_key = f"{item.get('id')}_{item.get('category', 'movie')}"
        if cache_key in self._links_cache:
            # Use cached links
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
            # Cache the links
            self._links_cache[cache_key] = links
            self.after(0, lambda: self._on_links_done(links, item))

        self._links_thread = threading.Thread(target=run, daemon=True)
        self._links_thread.start()

    def _on_links_done(self, links, item):
        self._show_links(links, item)
        if links:
            self._set_status(
                f"找到 {len(links)} 个下载链接 – 点击链接在浏览器中打开"
            )
        else:
            self._set_status("未找到下载链接，请在豆瓣页面手动搜索")

    # ─── display helpers ──────────────────────────────────────────────────────

    def _clear_detail(self):
        self._detail_text.config(state="normal")
        self._detail_text.delete("1.0", "end")
        self._detail_text.config(state="disabled")

    def _clear_links(self):
        self._links_text.config(state="normal")
        self._links_text.delete("1.0", "end")
        self._links_text.config(state="disabled")
        self._link_urls = []

    def _show_detail(self, item):
        self._detail_text.config(state="normal")
        self._detail_text.delete("1.0", "end")

        title = item.get("title", "")
        year = item.get("year", "")
        rating = item.get("rating", "")
        summary = item.get("summary", "")
        url = item.get("url", "")
        category = item.get("category", "")

        cat_label = {"movie": "电影", "book": "图书", "music": "音乐"}.get(category, "")

        lines = []
        lines.append(f"【{title}】")
        if year:
            lines.append(f"年份: {year}")
        if rating:
            lines.append(f"评分: ★ {rating}")
        if cat_label:
            lines.append(f"类型: {cat_label}")
        if summary:
            lines.append(f"\n简介: {summary}")
        if url:
            lines.append(f"\n豆瓣链接: {url}")

        self._detail_text.insert("end", "\n".join(lines))

        # Make the URL clickable
        if url:
            start = self._detail_text.search(url, "1.0", "end")
            if start:
                end = f"{start}+{len(url)}c"
                tag = f"detail_url_{id(url)}"
                self._detail_text.tag_add(tag, start, end)
                self._detail_text.tag_configure(
                    tag, foreground=ACCENT_LIGHT, underline=True
                )
                self._detail_text.tag_bind(
                    tag, "<Button-1>",
                    lambda _e, u=url: webbrowser.open(u),
                )
                self._detail_text.tag_bind(
                    tag, "<Enter>",
                    lambda _e: self._detail_text.config(cursor="hand2"),
                )
                self._detail_text.tag_bind(
                    tag, "<Leave>",
                    lambda _e: self._detail_text.config(cursor="arrow"),
                )

        self._detail_text.config(state="disabled")

    def _show_links(self, links, item):
        self._links_text.config(state="normal")
        self._links_text.delete("1.0", "end")
        self._link_urls = []

        if not links:
            self._links_text.insert("end", "未找到下载链接。\n\n建议直接访问豆瓣资源页面查找。")
            self._links_text.config(state="disabled")
            return

        for i, link in enumerate(links):
            source = link.get("source", "")
            name = link.get("name", "")
            url = link.get("url", "")
            magnet = link.get("magnet", "")

            # Source badge
            self._links_text.insert("end", f"[{source}] ", "source")

            # Link name / URL
            if url:
                tag = f"link_{i}"
                self._links_text.insert("end", name or url, tag)
                self._links_text.tag_configure(
                    tag, foreground=ACCENT_LIGHT, underline=True
                )
                self._links_text.tag_bind(
                    tag, "<Button-1>",
                    lambda _e, u=url: webbrowser.open(u),
                )
                self._links_text.tag_bind(
                    tag, "<Enter>",
                    lambda _e: self._links_text.config(cursor="hand2"),
                )
                self._links_text.tag_bind(
                    tag, "<Leave>",
                    lambda _e: self._links_text.config(cursor="arrow"),
                )
            else:
                self._links_text.insert("end", name)

            self._links_text.insert("end", "\n")

            # Magnet link on second line if present
            if magnet:
                m_tag = f"magnet_{i}"
                self._links_text.insert("end", "  🧲 ", "source")
                self._links_text.insert("end", magnet[:72] + "…", m_tag)
                self._links_text.tag_configure(
                    m_tag, foreground=SUCCESS, underline=True
                )
                self._links_text.tag_bind(
                    m_tag, "<Button-1>",
                    lambda _e, u=magnet: webbrowser.open(u),
                )
                self._links_text.tag_bind(
                    m_tag, "<Enter>",
                    lambda _e: self._links_text.config(cursor="hand2"),
                )
                self._links_text.tag_bind(
                    m_tag, "<Leave>",
                    lambda _e: self._links_text.config(cursor="arrow"),
                )
                self._links_text.insert("end", "\n")

            self._links_text.insert("end", "\n")

        self._links_text.config(state="disabled")

    def _set_status(self, msg):
        self._status_var.set(msg)

    # ─── history management ───────────────────────────────────────────────────

    def _load_history(self):
        """Load search history from JSON file."""
        if not os.path.exists(self._history_file):
            return []
        try:
            with open(self._history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_to_history(self, keyword, category):
        """Save a search to history."""
        entry = {
            'keyword': keyword,
            'category': category,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        # Remove duplicates (same keyword and category)
        self._history = [h for h in self._history 
                        if not (h['keyword'] == keyword and h['category'] == category)]
        # Add to front
        self._history.insert(0, entry)
        # Keep only last 50 entries
        self._history = self._history[:50]
        # Save to file
        try:
            with open(self._history_file, 'w', encoding='utf-8') as f:
                json.dump(self._history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _show_history(self):
        """Show history window."""
        if not self._history:
            messagebox.showinfo("历史记录", "暂无搜索历史")
            return

        history_win = tk.Toplevel(self)
        history_win.title("搜索历史")
        history_win.geometry("600x400")
        history_win.configure(bg=BG)
        history_win.transient(self)
        history_win.grab_set()

        tk.Label(
            history_win, text="搜索历史记录", bg=BG, fg=TEXT,
            font=("Segoe UI", 14, "bold"), pady=10
        ).pack()

        # Create frame for list
        list_frame = tk.Frame(history_win, bg=SURFACE)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        history_list = tk.Listbox(
            list_frame, bg=SURFACE, fg=TEXT,
            selectbackground=ACCENT, selectforeground="white",
            activestyle="none", font=("Segoe UI", 10),
            relief="flat", yscrollcommand=scrollbar.set,
            cursor="hand2"
        )
        history_list.pack(fill="both", expand=True)
        scrollbar.config(command=history_list.yview)

        # Populate history
        cat_labels = {"movie": "电影", "book": "图书", "music": "音乐"}
        for entry in self._history:
            cat_label = cat_labels.get(entry['category'], entry['category'])
            display = f"{entry['keyword']} [{cat_label}] - {entry['timestamp']}"
            history_list.insert("end", display)

        # Buttons frame
        btn_frame = tk.Frame(history_win, bg=BG)
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        def on_search_again():
            sel = history_list.curselection()
            if not sel:
                messagebox.showwarning("提示", "请选择一条历史记录")
                return
            idx = sel[0]
            entry = self._history[idx]
            history_win.destroy()
            # Set search parameters and search
            self._search_var.set(entry['keyword'])
            self._cat_var.set(entry['category'])
            self._do_search()

        def on_clear_history():
            if messagebox.askyesno("确认", "确定要清空所有历史记录吗？"):
                self._history = []
                try:
                    if os.path.exists(self._history_file):
                        os.remove(self._history_file)
                except Exception:
                    pass
                history_win.destroy()
                messagebox.showinfo("提示", "历史记录已清空")

        tk.Button(
            btn_frame, text="再次搜索", command=on_search_again,
            bg=ACCENT, fg="white", activebackground=ACCENT_LIGHT,
            font=("Segoe UI", 10, "bold"), relief="flat",
            padx=18, pady=6, cursor="hand2"
        ).pack(side="left", padx=5)

        tk.Button(
            btn_frame, text="清空历史", command=on_clear_history,
            bg=DANGER, fg="white", activebackground="#dc2626",
            font=("Segoe UI", 10, "bold"), relief="flat",
            padx=18, pady=6, cursor="hand2"
        ).pack(side="left", padx=5)

        tk.Button(
            btn_frame, text="关闭", command=history_win.destroy,
            bg=SURFACE, fg=TEXT, activebackground=TEXT_DIM,
            font=("Segoe UI", 10), relief="flat",
            padx=18, pady=6, cursor="hand2"
        ).pack(side="right", padx=5)

        # Double-click to search
        history_list.bind("<Double-Button-1>", lambda _e: on_search_again())


if __name__ == "__main__":
    app = App()
    app.mainloop()
