from __future__ import annotations

from prompt_toolkit.styles import Style

# Catppuccin Mocha Palette constants
CATPPUCCIN_MOCHA = {
    "base": "#1e1e2e",
    "mantle": "#181825",
    "crust": "#11111b",
    "surface0": "#313244",
    "surface1": "#45475a",
    "surface2": "#585b70",
    "overlay0": "#6c7086",
    "overlay1": "#7f849c",
    "overlay2": "#9399b2",
    "subtext0": "#a6adc8",
    "subtext1": "#bac2de",
    "text": "#cdd6f4",
    "lavender": "#b4befe",
    "blue": "#89b4fa",
    "sapphire": "#74c7ec",
    "sky": "#89dceb",
    "teal": "#94e2d5",
    "green": "#a6e3a1",
    "yellow": "#f9e2af",
    "peach": "#fab387",
    "maroon": "#eba0ac",
    "red": "#f38ba8",
    "mauve": "#cba6f7",
    "pink": "#f5c2e7",
}

# OpenCode prompt_toolkit theme
PT_STYLE = Style.from_dict(
    {
        # Prompt
        "prompt.symbol": f"{CATPPUCCIN_MOCHA['sapphire']} bold",
        "prompt.text": f"{CATPPUCCIN_MOCHA['mauve']} bold",
        "prompt.arrow": f"{CATPPUCCIN_MOCHA['blue']}",
        "prompt.user": f"{CATPPUCCIN_MOCHA['text']} bold",
        # Bottom Toolbar
        "bottom-toolbar": f"bg:{CATPPUCCIN_MOCHA['mantle']} {CATPPUCCIN_MOCHA['text']}",
        "bottom-toolbar.badge": f"bg:{CATPPUCCIN_MOCHA['surface0']} {CATPPUCCIN_MOCHA['mauve']} bold",
        "bottom-toolbar.key": f"bg:{CATPPUCCIN_MOCHA['surface0']} {CATPPUCCIN_MOCHA['blue']} bold",
        "bottom-toolbar.val": f"bg:{CATPPUCCIN_MOCHA['mantle']} {CATPPUCCIN_MOCHA['subtext0']}",
        "bottom-toolbar.model": f"bg:{CATPPUCCIN_MOCHA['surface0']} {CATPPUCCIN_MOCHA['green']} bold",
        "bottom-toolbar.schema": f"bg:{CATPPUCCIN_MOCHA['surface0']} {CATPPUCCIN_MOCHA['yellow']} bold",
        "bottom-toolbar.timer": f"bg:{CATPPUCCIN_MOCHA['mantle']} {CATPPUCCIN_MOCHA['overlay2']}",
        "bottom-toolbar.tokens": f"bg:{CATPPUCCIN_MOCHA['surface0']} {CATPPUCCIN_MOCHA['sapphire']} bold",
        # Completion menu popup
        "completion-menu": f"bg:{CATPPUCCIN_MOCHA['mantle']} {CATPPUCCIN_MOCHA['text']}",
        "completion-menu.completion": f"bg:{CATPPUCCIN_MOCHA['mantle']} {CATPPUCCIN_MOCHA['subtext1']}",
        "completion-menu.completion.current": f"bg:{CATPPUCCIN_MOCHA['mauve']} {CATPPUCCIN_MOCHA['crust']} bold",
        "completion-menu.meta": f"bg:{CATPPUCCIN_MOCHA['surface0']} {CATPPUCCIN_MOCHA['overlay2']} italic",
        "completion-menu.meta.current": f"bg:{CATPPUCCIN_MOCHA['blue']} {CATPPUCCIN_MOCHA['crust']} bold",
        "completion-menu.multi-column-meta": f"bg:{CATPPUCCIN_MOCHA['surface0']} {CATPPUCCIN_MOCHA['subtext0']} italic",
        "scrollbar.background": f"bg:{CATPPUCCIN_MOCHA['crust']}",
        "scrollbar.button": f"bg:{CATPPUCCIN_MOCHA['surface1']}",
    }
)
