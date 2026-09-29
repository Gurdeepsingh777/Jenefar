from __future__ import annotations

import shutil
import subprocess
import urllib.parse
from pathlib import Path


def preferred_browser() -> str | None:
    for binary in ("firefox", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(binary)
        if found:
            return found
    return None


def open_url(url: str) -> dict[str, object]:
    browser = preferred_browser()
    if browser:
        subprocess.Popen([browser, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"browser": Path(browser).name, "url": url}

    opener = shutil.which("xdg-open")
    if opener:
        subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"browser": "xdg-open", "url": url}

    raise RuntimeError("No supported browser was found. Install Firefox or Google Chrome.")


def play_youtube(query: str) -> dict[str, object]:
    query = " ".join(query.split()).strip()
    if not query:
        raise ValueError("YouTube search query cannot be empty.")
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    return open_url(url)


def play_local_media(path: str) -> dict[str, object]:
    candidate = Path(path).expanduser().resolve()
    vlc = shutil.which("vlc")
    if not vlc:
        raise RuntimeError("VLC is not installed.")
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    subprocess.Popen([vlc, "--play-and-exit", str(candidate)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"player": "vlc", "path": str(candidate)}


def first_mp3_in_folder(path: str) -> dict[str, object]:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)

    matches = sorted(candidate for candidate in root.rglob("*.mp3") if candidate.is_file())
    if not matches:
        raise FileNotFoundError(f"No MP3 file found under {root}")
    return play_local_media(str(matches[0]))
