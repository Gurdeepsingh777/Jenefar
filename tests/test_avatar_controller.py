from jenefar.avatar.controller import AvatarController


def test_avatar_controller_publishes_current_state():
    controller = AvatarController()
    subscriber = controller.subscribe()

    initial = subscriber.get_nowait()
    assert initial["state"] == "idle"

    controller.publish("thinking", "Processing…")
    event = subscriber.get_nowait()
    assert event["state"] == "thinking"
    assert event["text"] == "Processing…"


def test_avatar_unsubscribe():
    controller = AvatarController()
    subscriber = controller.subscribe()
    controller.unsubscribe(subscriber)
    controller.publish("speaking", "Hello")
    assert controller.current()["state"] == "speaking"
    assert subscriber.empty()
