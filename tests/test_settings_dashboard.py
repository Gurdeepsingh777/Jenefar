from pathlib import Path

from jenefar.avatar.settings import UISettings
from jenefar.evaluation.dashboard import render_dashboard


def test_ui_settings_only_persists_allowlisted_values(tmp_path: Path):
    settings = UISettings(tmp_path / "settings.json")
    value = settings.update({
        "theme": "dark",
        "avatar_port": 9000,
        "OPENAI_API_KEY": "must-not-persist",
    })
    assert value["theme"] == "dark"
    assert "OPENAI_API_KEY" not in value


def test_dashboard_renders_empty_state(tmp_path: Path):
    html = render_dashboard(tmp_path / "eval.jsonl")
    assert "Jenefar Evaluation Dashboard" in html


def test_avatar_server_serves_browser_voice_endpoint():
    from jenefar.avatar.controller import AvatarController
    from jenefar.avatar.server import AvatarServer
    import urllib.request
    import json

    controller = AvatarController()
    server = AvatarServer(
        controller,
        host="127.0.0.1",
        port=0,
        voice_handler=lambda text: {"ok": True, "echo": text},
    )
    server.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/voice/text",
            data=json.dumps({"text": "Hello Jenefar"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        payload = json.loads(
            urllib.request.urlopen(request, timeout=2).read().decode("utf-8")
        )
        assert payload == {"ok": True, "echo": "Hello Jenefar"}
    finally:
        server.stop()


def test_avatar_server_serves_health_endpoint():
    from jenefar.avatar.controller import AvatarController
    from jenefar.avatar.server import AvatarServer
    import urllib.request
    import json

    controller = AvatarController()
    server = AvatarServer(controller, host="127.0.0.1", port=0)
    # ThreadingHTTPServer assigns an ephemeral port when port=0.
    server.port = server._server.server_address[1]
    server.start()
    try:
        payload = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:{server.port}/health", timeout=2
        ).read().decode("utf-8"))
        assert payload["status"] == "ok"
        assert "avatar" in payload
        assert "vrm_available" in payload
    finally:
        server.stop()
