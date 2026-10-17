
def test_network_ip_info_tool_is_registered_read_only_and_does_not_require_approval(monkeypatch):
    import json
    import jenefar.tools.broker as broker_module
    from jenefar.tools.broker import ToolBroker

    monkeypatch.setattr(
        broker_module,
        "get_network_ip_info",
        lambda: {
            "local_ipv4": [{"address": "192.168.1.20", "interface": "wlan0"}],
            "local_ipv6": [],
            "public_ipv4": None,
            "public_ipv4_status": "unavailable",
            "network_scan_performed": False,
        },
    )
    broker = ToolBroker(require_confirmation=True)
    schemas = {tool["name"]: tool for tool in broker.schemas(allow_action_tools=True)}

    assert "network_ip_info" in schemas
    result = json.loads(broker.invoke("network_ip_info", {}))

    assert result["status"] == "ok"
    assert result["result"]["network_scan_performed"] is False
    assert result["result"]["local_ipv4"][0]["address"] == "192.168.1.20"
    assert not broker.pending
