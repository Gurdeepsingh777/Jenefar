from __future__ import annotations

ONLINE_ONLY = (
    ("web_search", "Current web/research queries"),
    ("online_download", "Internet downloads and remote asset provisioning"),
    ("youtube", "YouTube search/playback"),
    ("song_recognition", "Recognizing an unknown song from microphone audio"),
    ("github_research", "Live GitHub repository retrieval"),
)

LOCAL_AVAILABLE = (
    ("local_files", "Inspect and edit authorized local workspace files"),
    ("python_execution", "Run authorized local Python files after approval"),
    ("local_media", "Play local audio/video through installed players"),
    ("local_llm", "Use the configured local model when available"),
)


def unavailable_online_items() -> list[dict[str, str]]:
    return [{"capability": key, "description": description} for key, description in ONLINE_ONLY]


def local_items() -> list[dict[str, str]]:
    return [{"capability": key, "description": description} for key, description in LOCAL_AVAILABLE]
