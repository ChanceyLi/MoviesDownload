"""
Application configuration: themes, default settings, and persistence helpers.
No GUI imports – safe to import in test environments.
"""

import json
import os

# ─── theme definitions ────────────────────────────────────────────────────────
THEMES = {
    "深色紫": {
        "BG": "#1e1e2e", "SURFACE": "#2a2a3e", "ACCENT": "#7c3aed",
        "ACCENT_LIGHT": "#a78bfa", "TEXT": "#e2e8f0", "TEXT_DIM": "#94a3b8",
        "SUCCESS": "#22c55e", "DANGER": "#ef4444", "ENTRY_BG": "#12121e",
    },
    "深色蓝": {
        "BG": "#0f172a", "SURFACE": "#1e293b", "ACCENT": "#2563eb",
        "ACCENT_LIGHT": "#60a5fa", "TEXT": "#e2e8f0", "TEXT_DIM": "#94a3b8",
        "SUCCESS": "#22c55e", "DANGER": "#ef4444", "ENTRY_BG": "#0a0f1e",
    },
    "深色绿": {
        "BG": "#0f1f0f", "SURFACE": "#1a2e1a", "ACCENT": "#16a34a",
        "ACCENT_LIGHT": "#4ade80", "TEXT": "#e2e8f0", "TEXT_DIM": "#94a3b8",
        "SUCCESS": "#22c55e", "DANGER": "#ef4444", "ENTRY_BG": "#0a150a",
    },
    "浅色": {
        "BG": "#f1f5f9", "SURFACE": "#ffffff", "ACCENT": "#7c3aed",
        "ACCENT_LIGHT": "#6d28d9", "TEXT": "#1e293b", "TEXT_DIM": "#64748b",
        "SUCCESS": "#16a34a", "DANGER": "#dc2626", "ENTRY_BG": "#e2e8f0",
    },
}

SETTINGS_FILE = "settings.json"
DOWNLOAD_HISTORY_FILE = "download_history.json"

DEFAULT_SETTINGS = {
    "theme": "深色紫",
    "download_path": os.path.expanduser("~/Downloads"),
    "max_concurrent_downloads": 3,
    "auto_open_after_download": False,
    "open_with": "",
}


def load_settings():
    """Load settings from file, filling in any missing keys from defaults."""
    settings = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            settings.update(saved)
        except Exception:
            pass
    return settings


def save_settings(settings):
    """Persist settings dict to SETTINGS_FILE."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
