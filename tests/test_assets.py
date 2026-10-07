from pathlib import Path

from jenefar.assets.provisioning import ALLOWED_HOSTS, ResourceSpec, _validate_url


def test_resource_url_allowlist():
    _validate_url("https://github.com/example/project/archive/main.zip")
    _validate_url("https://www.openslr.org/resources/26/sim_rir_16k.zip")
    assert "github.com" in ALLOWED_HOSTS


def test_resource_rejects_non_https_or_unlisted():
    try:
        _validate_url("http://github.com/example/project.zip")
    except ValueError:
        pass
    else:
        raise AssertionError("http URL should be rejected")

    try:
        _validate_url("https://example.com/resource.zip")
    except ValueError:
        pass
    else:
        raise AssertionError("unlisted host should be rejected")


def test_resource_spec_has_license():
    spec = ResourceSpec(
        "demo",
        "https://github.com/example/demo.zip",
        "demo.zip",
        "MIT",
        "example",
        100,
    )
    assert spec.license


def test_avatar_paths_are_anchored_to_repository_root(tmp_path, monkeypatch):
    import run

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JENEFAR_PREMIUM_AVATAR", "0")
    target = Path(run.__file__).resolve().parent / "data" / "avatar" / "AvatarSample_A_1.0.vrm.glb"
    result = run.prepare_avatar_model()
    if target.exists():
        assert result == target
    else:
        assert result is None or result != tmp_path / "data" / "avatar" / "AvatarSample_A_1.0.vrm.glb"


def test_avatar_server_rejects_oversized_request_body():
    from jenefar.avatar.server import _AvatarHandler

    class Headers(dict):
        pass

    handler = object.__new__(_AvatarHandler)
    handler.headers = Headers(
        {"Content-Length": str(_AvatarHandler.MAX_REQUEST_BODY_BYTES + 1)}
    )
    try:
        handler._read_json()
    except ValueError as exc:
        assert "request body too large" in str(exc)
    else:
        raise AssertionError("oversized request body was accepted")
