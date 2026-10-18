from __future__ import annotations

import json
from urllib.request import Request, urlopen

from jenefar.avatar.controller import AvatarController
from jenefar.avatar.server import AvatarServer


def test_runtime_status_history_and_cancel_http_routes():
    server = AvatarServer(
        AvatarController(),
        port=0,
        runtime_status_handler=lambda: {"schema_version": 1, "current": {"state": "running"}},
        runtime_tasks_handler=lambda **kwargs: {
            "persistent": True,
            "items": [],
            "filters": kwargs,
        },
        runtime_cancel_handler=lambda **kwargs: {
            "cancelled": True,
            "reason": kwargs.get("reason", ""),
        },
    )
    server.start()
    try:
        with urlopen(server.url + "runtime/status", timeout=2) as response:
            status = json.loads(response.read())
            assert response.status == 200
            assert status["current"]["state"] == "running"

        with urlopen(server.url + "runtime/tasks?search=jenefar&state=completed&limit=5", timeout=2) as response:
            history = json.loads(response.read())
            assert response.status == 200
            assert history["persistent"] is True
            assert history["filters"]["search"] == "jenefar"
            assert history["filters"]["state"] == "completed"
            assert history["filters"]["limit"] == 5

        request = Request(
            server.url + "runtime/cancel",
            data=json.dumps({"reason": "test cancellation"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            result = json.loads(response.read())
            assert response.status == 200
            assert result["cancelled"] is True
            assert result["reason"] == "test cancellation"
    finally:
        server.stop()
