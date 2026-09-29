from jenefar.offline.capabilities import unavailable_online_items


def test_offline_capability_list_is_present():
    values = unavailable_online_items()
    names = {item["capability"] for item in values}
    assert "youtube" in names
    assert "online_download" in names
