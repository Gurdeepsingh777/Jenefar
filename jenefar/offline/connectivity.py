from __future__ import annotations

import socket
import urllib.request


def internet_available(timeout: float = 2.0) -> bool:
    checks = (
        ("https://www.google.com/generate_204", 204),
        ("https://api.github.com", 200),
    )
    for url, expected in checks:
        try:
            request = urllib.request.Request(
                url,
                method="HEAD",
                headers={"User-Agent": "Jenefar/1.0"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status in {200, 204, 301, 302, expected}:
                    return True
        except Exception:
            continue
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=timeout):
            return True
    except OSError:
        return False
