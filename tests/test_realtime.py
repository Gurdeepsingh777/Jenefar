from jenefar.realtime.server import RealtimeSessionError, create_ephemeral_session


def test_realtime_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    try:
        create_ephemeral_session()
    except RealtimeSessionError as exc:
        assert "OPENAI_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected missing API key error")
