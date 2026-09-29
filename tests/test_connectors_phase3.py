from jenefar.connectors.base import Connector, ConnectorAction, ConnectorManifest
from jenefar.connectors.manager import ConnectorManager


def test_connector_manifest_and_execution():
    connector = Connector(
        ConnectorManifest(
            name="demo",
            version="1.0",
            description="Test connector.",
            online_required=False,
            actions=(ConnectorAction("echo", "Echo input."),),
        ),
        {"echo": lambda args: {"value": args["value"]}},
    )
    assert connector.execute("echo", {"value": "ok"})["value"] == "ok"


def test_connector_manager_lists_builtin_metadata():
    manager = ConnectorManager()
    names = {item["name"] for item in manager.list()}
    assert "browser" in names
    assert "github" in names
    assert "web" in names
