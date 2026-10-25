from jenefar.voice.wakeword import WakeWord


def test_hello_jenefar_can_be_identified_separately():
    wake = WakeWord(["Hi Jenefar", "Hello Jenefar"])
    assert wake.matched_phrase("Hello Jenefar") == "hello jenefar"
    assert wake.matched_phrase("Hello Jenefar tell me a joke") == "hello jenefar"
    assert wake.matched_phrase("Hi Jenefar") == "hi jenefar"


def test_wakeword_removal_stays_normalized():
    wake = WakeWord(["Hello Jenefar"])
    assert wake.remove_wake_phrase("Hello Jenefar Kya haal hai?") == "kya haal hai?"


def test_wakeword_ignores_punctuation_and_commas():
    wake = WakeWord(["Hi Jenefar", "Hello Jenefar"])
    assert wake.matched_phrase("Hello, Jenefar") == "hello jenefar"
    assert wake.matched_phrase("Hello, jenefar") == "hello jenefar"
    assert wake.matched_phrase("Hello, Jenefar. scan my network") == "hello jenefar"
    assert wake.remove_wake_phrase("Hello, Jenefar. scan my network and check live host.") == (
        "scan my network and check live host."
    )
    assert wake.remove_wake_phrase("Hello Jenefar Kya haal hai?") == "kya haal hai?"

from jenefar.agents.llm_agent import BaseLLMAgent


def test_hinglish_instruction_is_explicit():
    text = BaseLLMAgent._language_instruction("Hinglish")
    assert "Hinglish" in text
    assert "Roman Hindi" in text
    assert "code" in text


def test_normal_language_has_no_hinglish_override():
    assert BaseLLMAgent._language_instruction(None) == ""
