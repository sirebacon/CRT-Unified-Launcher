"""
CRT phosphor-green theme constants.

Provides:
  - THEME_PATH : path to crt_green_theme.json (passed to ctk.set_default_color_theme)
  - Color literals for explicit widget overrides
  - Font tuples for consistent typography
"""
from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Theme file
# ---------------------------------------------------------------------------

THEME_PATH: str = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets",
    "crt_green_theme.json",
)

# ---------------------------------------------------------------------------
# Phosphor-green palette
# ---------------------------------------------------------------------------

GREEN_BRIGHT: str = "#39ff14"   # neon phosphor — primary text / accents
GREEN_MID: str    = "#22cc22"   # section headers, secondary labels
GREEN_DIM: str    = "#0d5a0d"   # disabled / placeholder
GREEN_DARK: str   = "#0d2a0d"   # button default background
GREEN_HOVER: str  = "#1a4a1a"   # button hover background
BORDER: str       = "#2a6a2a"   # widget borders

BG_ROOT: str      = "#0a0a0a"   # main window background
BG_FRAME: str     = "#111111"   # section frame background
BG_OUTPUT: str    = "#050a05"   # output panel text area

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

FONT_SECTION: tuple = ("Consolas", 11, "bold")
FONT_BUTTON:  tuple = ("Consolas", 12)
FONT_OUTPUT:  tuple = ("Consolas", 11)
