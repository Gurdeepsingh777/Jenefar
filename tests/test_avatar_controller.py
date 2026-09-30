from jenefar.avatar.controller import AvatarController


def test_avatar_controller_publishes_current_state():
    controller = AvatarController()
    subscriber = controller.subscribe()

    initial = subscriber.get_nowait()
    assert initial["state"] == "idle"
    assert initial["level"] == 0.0

    controller.publish("thinking", "Processing…", level=0.4)
    event = subscriber.get_nowait()
    assert event["state"] == "thinking"
    assert event["text"] == "Processing…"
    assert event["level"] == 0.4


def test_avatar_unsubscribe():
    controller = AvatarController()
    subscriber = controller.subscribe()
    subscriber.get_nowait()
    controller.unsubscribe(subscriber)
    controller.publish("speaking", "Hello")
    assert controller.current()["state"] == "speaking"
    assert subscriber.empty()



def test_avatar_events_are_recoverable_for_browser_clients():
    controller = AvatarController()
    subscriber = controller.subscribe()
    subscriber.get_nowait()

    controller.publish("speaking", "Haan, main ready hoon.", task_id="abc")
    event = subscriber.get_nowait()

    assert event["task_id"] == "abc"
    assert event["state"] == "speaking"
    assert event["text"] == "Haan, main ready hoon."
