"""
Font Management Module

Handles loading local fonts and optionally downloading Google Fonts.
"""

from pathlib import Path

# Default font paths relative to project root
FONTS_DIR = "assets/fonts"

# Default font files
DEFAULT_FONTS = {
    "bold": "Roboto-Bold.ttf",
    "light": "Roboto-Light.ttf",
    "regular": "Roboto-Regular.ttf",
}


def get_fonts_dir() -> Path:
    """
    Get the fonts directory path.

    Returns:
        Path to fonts directory
    """
    # Try relative to current file first
    current_dir = Path(__file__).parent
    fonts_path = current_dir.parent / FONTS_DIR

    if fonts_path.exists():
        return fonts_path

    # Fallback to current working directory
    fonts_path = Path.cwd() / FONTS_DIR
    if fonts_path.exists():
        return fonts_path

    # Create fonts directory if it doesn't exist
    fonts_path.mkdir(parents=True, exist_ok=True)
    return fonts_path


def load_fonts() -> dict[str, str] | None:
    """
    Load fonts for poster generation.

    Returns:
        Dictionary with font file paths (bold, light, regular) or None if loading fails.
    """
    fonts_dir = get_fonts_dir()

    # Check if default fonts exist
    font_paths = {}
    for key, filename in DEFAULT_FONTS.items():
        font_path = fonts_dir / filename
        if font_path.exists():
            font_paths[key] = str(font_path)
        else:
            # If any default font is missing, return None
            return None

    return font_paths if font_paths else None


def get_available_fonts() -> list:
    """
    Get list of available .ttf and .otf font files.

    Returns:
        List of font filenames
    """
    fonts_dir = get_fonts_dir()
    if not fonts_dir.exists():
        return []

    font_files = []
    for ext in ["*.ttf", "*.otf"]:
        font_files.extend(fonts_dir.glob(ext))

    return [f.name for f in font_files]


def font_info() -> dict[str, str]:
    """
    Get information about available fonts.

    Returns:
        Dictionary with font info
    """
    fonts_dir = get_fonts_dir()
    fonts = load_fonts()

    return {
        "fonts_dir": str(fonts_dir),
        "default_fonts_loaded": fonts is not None,
        "available_fonts": get_available_fonts(),
    }
