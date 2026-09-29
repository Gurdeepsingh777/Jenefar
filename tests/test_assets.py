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
