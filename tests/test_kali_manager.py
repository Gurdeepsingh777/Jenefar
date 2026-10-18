from jenefar.execution.scope import ScopePolicy
from jenefar.tools.kali import KaliToolManager


def test_kali_catalog_has_tactic_metadata():
    manager = KaliToolManager()
    items = manager.catalog_list(tactic="Discovery")
    assert items
    assert all("tactic" in item and "installed" in item for item in items)


def test_kali_execution_rejects_unknown_tool():
    manager = KaliToolManager()
    try:
        manager.execute(tool="definitely-not-a-kali-tool", args=[], target="", timeout=1)
    except (ValueError, FileNotFoundError):
        pass
    else:
        raise AssertionError("Unknown tool should be rejected.")


def test_kali_catalog_natural_language_filter_does_not_return_empty_for_network_scanning():
    manager = KaliToolManager()
    items = manager.catalog_list(category="network scanning tools", limit=100)
    names = {item["name"].casefold() for item in items}
    assert items
    assert any(name in names for name in ("nmap", "masscan", "rustscan"))


def _make_fake_cli(tmp_path, name):
    command = tmp_path / name
    command.write_text(
        """#!/bin/sh
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
  echo 'Usage: custom command [OPTIONS] TARGET'
  echo 'Read-only fake help used in unit tests.'
  exit 0
fi
echo 'FAKE_TOOL_RAN'
""",
        encoding="utf-8",
    )
    command.chmod(0o755)
    return command

def test_unlisted_path_tool_is_discovered_and_local_help_is_read(tmp_path, monkeypatch):
    _make_fake_cli(tmp_path, "customaudit")
    monkeypatch.setenv("PATH", str(tmp_path))

    manager = KaliToolManager()
    matches = manager.catalog_list(query="customaudit", include_all=True, installed_only=True)

    assert any(item["name"] == "customaudit" for item in matches)
    result = manager.inspect_tool(tool="customaudit")

    assert result["installed"] is True
    assert result["path"].endswith("customaudit")
    assert "Usage: custom command" in result["help"]
    assert result["inspected_for_this_session"] is True


def test_new_network_tool_must_be_inspected_then_target_must_be_authorized(tmp_path, monkeypatch):
    _make_fake_cli(tmp_path, "customscan")
    monkeypatch.setenv("PATH", str(tmp_path))
    manager = KaliToolManager(scope=ScopePolicy(["lab.example.com"]))

    try:
        manager.preview(tool="customscan", args=["lab.example.com"], timeout=10)
    except PermissionError as exc:
        assert "kali_tool_help first" in str(exc)
    else:
        raise AssertionError("An unfamiliar tool must be inspected before execution.")

    manager.inspect_tool(tool="customscan")
    preview = manager.preview(tool="customscan", args=["lab.example.com"], timeout=10)
    assert preview["scope_checked"] is True
    assert preview["targets"] == ["lab.example.com"]
    assert "customscan" in preview["command"]

    try:
        manager.preview(tool="customscan", args=["outside.example.org"], timeout=10)
    except PermissionError as exc:
        assert "outside the configured authorization scope" in str(exc)
    else:
        raise AssertionError("Out-of-scope remote targets must be rejected.")


def test_nested_out_of_scope_ip_cannot_hide_in_tool_script_arguments(tmp_path, monkeypatch):
    _make_fake_cli(tmp_path, "customscan")
    monkeypatch.setenv("PATH", str(tmp_path))
    manager = KaliToolManager(scope=ScopePolicy(["lab.example.com"]))
    manager.inspect_tool(tool="customscan")

    try:
        manager.preview(
            tool="customscan",
            args=["-x", "set RHOSTS 8.8.8.8; run"],
            target="lab.example.com",
            timeout=10,
        )
    except PermissionError as exc:
        assert "8.8.8.8" in str(exc)
    else:
        raise AssertionError("A nested out-of-scope IP must not be authorized by a different target field.")


def test_mac_bssid_is_a_scope_checked_target_for_discovered_wireless_tools(tmp_path, monkeypatch):
    _make_fake_cli(tmp_path, "airscan")
    monkeypatch.setenv("PATH", str(tmp_path))
    manager = KaliToolManager(scope=ScopePolicy(["AA:BB:CC:DD:EE:FF"]))
    manager.inspect_tool(tool="airscan")

    preview = manager.preview(
        tool="airscan",
        args=["-b", "aa:bb:cc:dd:ee:ff"],
        timeout=10,
    )

    assert preview["targets"] == ["aa:bb:cc:dd:ee:ff"]
    assert preview["scope_checked"] is True


def test_local_file_arguments_are_not_mistaken_for_network_targets(tmp_path, monkeypatch):
    _make_fake_cli(tmp_path, "custompass")
    monkeypatch.setenv("PATH", str(tmp_path))
    manager = KaliToolManager()
    manager.inspect_tool(tool="custompass")

    preview = manager.preview(tool="custompass", args=["hashes.txt"], timeout=10)

    assert preview["targets"] == []
    assert preview["scope_checked"] is False


def test_network_target_list_flags_are_rejected_even_when_target_field_is_authorized():
    manager = KaliToolManager(scope=ScopePolicy(["192.168.29.0/24"]))
    try:
        manager.preview(
            tool="nmap",
            args=["-sV", "-iL", "/tmp/host-list.txt"],
            target="192.168.29.10",
            timeout=30,
        )
    except PermissionError as exc:
        assert "blocks target-list/random-target flags" in str(exc)
    else:
        raise AssertionError("Target-list flags must not bypass target-by-target authorization.")
