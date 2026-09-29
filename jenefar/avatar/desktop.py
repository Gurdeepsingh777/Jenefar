from __future__ import annotations

import threading
import webbrowser


def launch_desktop(url: str) -> None:
    """Launch a native pywebview shell when available; otherwise open the browser."""
    try:
        import webview
    except Exception:
        webbrowser.open(url)
        return

    window = webview.create_window(
        "Jenefar AI",
        url,
        width=1440,
        height=920,
        min_size=(1024, 720),
        resizable=True,
    )
    webview.start()
