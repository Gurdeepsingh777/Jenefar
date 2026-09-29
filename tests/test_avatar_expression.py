from jenefar.avatar.expression import ExpressionEngine


def test_thinking_is_focused():
    result = ExpressionEngine().classify("thinking", "analyzing your request")
    assert result.name == "focused"


def test_waiting_approval_is_alert():
    result = ExpressionEngine().classify("waiting_approval", "A tool needs approval")
    assert result.name == "alert"


def test_successful_speaking_can_look_happy():
    result = ExpressionEngine().classify("speaking", "Done, the task completed successfully")
    assert result.name == "happy"
