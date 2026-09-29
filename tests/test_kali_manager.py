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
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown tool should be rejected.")
