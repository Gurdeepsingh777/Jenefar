from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_monitoring_workflow_covers_phase_branches():
    source = (ROOT / ".github/workflows/monitoring-check.yml").read_text()
    assert '"phase*"' in source
    assert 'jenefar/monitoring/**' in source
    assert 'requirements.txt' in source
    assert 'pyproject.toml' in source


def test_dashboard_has_telemetry_details():
    source = (ROOT / "jenefar/avatar/web/index.html").read_text()
    assert 'id="ram-detail"' in source
    assert 'id="gpu-load-detail"' in source
    assert 'id="telemetry-updated"' in source


def test_dashboard_telemetry_has_stale_state():
    source = (ROOT / "jenefar/avatar/web/app.js").read_text()
    assert 'STALE • TELEMETRY DELAYED' in source
    assert 'telemetryLastUpdate' in source
    assert 'setInterval(updateTelemetryFreshness, 2000)' in source


def test_dashboard_telemetry_css_has_states():
    source = (ROOT / "jenefar/avatar/web/style.css").read_text()
    assert '#system-telemetry-state[data-state="online"]' in source
    assert '#system-telemetry-state[data-state="stale"]' in source
    assert '#system-telemetry-state[data-state="offline"]' in source
