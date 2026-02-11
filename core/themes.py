"""Theme Management Module

Loads and manages poster color themes from JSON files.
"""

import json
from pathlib import Path

THEMES_DIR = Path("assets/themes")


def get_theme_path(name: str) -> Path:
    """Get path to theme JSON file."""
    return THEMES_DIR / f"{name}.json"


def get_available_themes() -> list[str]:
    """Get list of available theme names."""
    if not THEMES_DIR.exists():
        return []
    return [f.stem for f in THEMES_DIR.glob("*.json")]


def load_theme(name: str) -> dict[str, str] | None:
    """Load theme by name."""
    path = get_theme_path(name)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def get_theme_info(name: str) -> dict[str, str] | None:
    """Get theme metadata."""
    theme = load_theme(name)
    if not theme:
        return None
    return {
        "id": name,
        "name": theme.get("name", name),
        "description": theme.get("description", ""),
    }


def get_all_themes_info() -> list[dict[str, str]]:
    """Get metadata for all themes."""
    themes = get_available_themes()
    info = []
    for theme_name in themes:
        meta = get_theme_info(theme_name)
        if meta:
            info.append(meta)
    return sorted(info, key=lambda x: x["name"])
