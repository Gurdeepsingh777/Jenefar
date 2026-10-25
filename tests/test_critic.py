from jenefar.critic.verifier import Critique, Verifier


def test_simple_complexity_skips_critic():
    critique = Verifier().review("hi", "Haan, boliye.", complexity="simple")
    assert critique.skipped is True
    assert critique.passed is True


def test_empty_result_fails():
    critique = Verifier().review("edit example.py", "   ", complexity="standard")
    assert critique.passed is False
    assert "empty" in critique.notes.lower()


def test_claimed_file_without_tool_fails():
    critique = Verifier().review(
        "edit example.py",
        "I updated example.py and the tests passed.",
        complexity="standard",
        tool_trace=[],
    )
    assert critique.passed is False
    assert "tool" in critique.notes.lower()


def test_ignored_tool_error_fails():
    critique = Verifier().review(
        "run example.py",
        "All done, the file ran successfully.",
        complexity="hard",
        tool_trace=[{"name": "workspace_run_python", "status": "error", "result": "boom"}],
    )
    assert critique.passed is False
    assert "error" in critique.notes.lower()


def test_good_result_with_tool_passes():
    critique = Verifier().review(
        "edit example.py",
        "Edited example.py and added a docstring.",
        complexity="standard",
        tool_trace=[{"name": "workspace_edit_file", "status": "ok", "result": {"path": "example.py"}}],
    )
    assert critique.passed is True
    assert critique.skipped is False


def test_verify_passthrough_on_exception():
    class Broken(Verifier):
        def review(self, *args, **kwargs):
            raise RuntimeError("critic down")

    output = Broken().verify("task", "original answer", complexity="hard")
    assert output == "original answer"


def test_second_fail_appends_verify_note():
    output = Verifier().verify(
        "edit example.py",
        "I updated example.py",
        complexity="standard",
        tool_trace=[],
        critic_pass=1,
    )
    assert "I updated example.py" in output
    assert "could not verify" in output.lower()


def test_verify_empty_still_returns_usable_message():
    output = Verifier().verify("task", "  ")
    assert output.strip()
    assert "no usable result" in output.lower()
