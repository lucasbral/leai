from __future__ import annotations

from prompt_toolkit.styles import Style

# OpenCode minimalist modern prompt_toolkit theme
PT_STYLE = Style.from_dict(
    {
        # Prompt
        "prompt.symbol": "ansicyan bold",
        "prompt.text": "#ffffff bold",
        "prompt.arrow": "ansicyan",
        # Bottom Toolbar
        "bottom-toolbar": "bg:#1e1e2e #cdd6f4",
        "bottom-toolbar.key": "bg:#313244 #89b4fa bold",
        "bottom-toolbar.val": "bg:#1e1e2e #a6adc8",
        "bottom-toolbar.model": "bg:#313244 #a6e3a1 bold",
        "bottom-toolbar.schema": "bg:#313244 #f9e2af bold",
        "bottom-toolbar.timer": "bg:#1e1e2e #9399b2",
        # Completion menu popup
        "completion-menu": "bg:#1e1e2e #cdd6f4",
        "completion-menu.completion": "bg:#181825 #bac2de",
        "completion-menu.completion.current": "bg:#89b4fa #11111b bold",
        "completion-menu.meta": "bg:#313244 #a6adc8 italic",
        "completion-menu.meta.current": "bg:#74c7ec #11111b bold",
        "completion-menu.multi-column-meta": "bg:#313244 #a6adc8 italic",
        "scrollbar.background": "bg:#181825",
        "scrollbar.button": "bg:#45475a",
    }
)
