"""
共用圖表風格 — Dark Mode

所有圖表模組 import 這裡的設定，確保一致性。
"""
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from pathlib import Path

# ── 配色 ──────────────────────────────────────────────────────
# 背景 — 深藍灰，不是純黑
BG_FIG = "#1B1F2B"
BG_AXES = "#232838"
BG_TABLE_HEADER = "#2A3A5E"
BG_TABLE_ROW_EVEN = "#1E2333"
BG_TABLE_ROW_ODD = "#232838"
BG_TABLE_HIGHLIGHT = "#2E3A50"

# 漲跌（台灣慣例：漲紅跌綠，深色背景上稍提亮）
COLOR_UP = "#F06060"
COLOR_DOWN = "#3DDC84"

# 強調色 — 飽和鮮明
COLOR_ACCENT_ORANGE = "#FFa050"
COLOR_ACCENT_BLUE = "#5BC0EB"
COLOR_ACCENT_PURPLE = "#B49FDC"
COLOR_ACCENT_GOLD = "#F9CA24"
COLOR_ACCENT_TEAL = "#4ECDC4"
COLOR_ACCENT_CORAL = "#FF7979"

# 文字
COLOR_TEXT = "#E0E0E0"
COLOR_TEXT_LIGHT = "#AAAAAA"
COLOR_TEXT_MUTED = "#777777"
COLOR_TEXT_WHITE = "#FFFFFF"

# 網格 & 邊框
COLOR_GRID = "#3A3F50"
COLOR_BORDER = "#444966"
COLOR_SPINE = "#3A3F55"

# ── 字型 ──────────────────────────────────────────────────────
def setup_font():
    """設定中文字型，優先 Heiti TC Medium。"""
    font_candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode MS.ttf",
        "/Library/Fonts/Arial Unicode MS.ttf",
    ]
    for f in font_candidates:
        if Path(f).exists():
            fp = fm.FontProperties(fname=f)
            plt.rcParams["font.family"] = fp.get_name()
            break
    plt.rcParams["axes.unicode_minus"] = False


# ── 圖表共用設定 ──────────────────────────────────────────────
def apply_style():
    """套用全域 matplotlib 樣式。"""
    setup_font()
    plt.rcParams.update({
        "figure.facecolor": BG_FIG,
        "axes.facecolor": BG_AXES,
        "axes.edgecolor": COLOR_SPINE,
        "axes.labelcolor": COLOR_TEXT,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.grid": False,
        "text.color": COLOR_TEXT,
        "xtick.color": COLOR_TEXT_LIGHT,
        "ytick.color": COLOR_TEXT_LIGHT,
        "grid.color": COLOR_GRID,
        "grid.linewidth": 0.6,
        "grid.alpha": 0.7,
    })


def style_axes(ax):
    """套用單一 axes 的風格。"""
    ax.set_facecolor(BG_AXES)
    ax.tick_params(colors=COLOR_TEXT_LIGHT, labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor(COLOR_SPINE)
    ax.yaxis.grid(True, linestyle="-", color=COLOR_GRID, linewidth=0.6, alpha=0.7)
    ax.set_axisbelow(True)


def style_table(table, n_rows, highlight_row=None):
    """套用表格風格。

    Args:
        table: matplotlib table object
        n_rows: 資料列數（不含 header）
        highlight_row: 要高亮的 row index（1-based，header=0）
    """
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor(COLOR_BORDER)
        cell.set_linewidth(0.8)
        if row == 0:
            cell.set_facecolor(BG_TABLE_HEADER)
            cell.set_text_props(color=COLOR_TEXT_WHITE, fontweight="bold")
        else:
            if highlight_row is not None and row == highlight_row:
                cell.set_facecolor(BG_TABLE_HIGHLIGHT)
            elif row % 2 == 0:
                cell.set_facecolor(BG_TABLE_ROW_EVEN)
            else:
                cell.set_facecolor(BG_TABLE_ROW_ODD)
