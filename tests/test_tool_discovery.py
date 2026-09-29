from jenefar.tools.discovery import discover_tools

def test_discovery_returns_known_tools():
    tools = discover_tools()
    names = {tool.name for tool in tools}
    assert "nmap" in names
    assert "sqlmap" in names

def test_custom_tool_is_included():
    tool = discover_tools(("mytool",))[-1]
    assert tool.name == "mytool"
    assert tool.category == "custom"
