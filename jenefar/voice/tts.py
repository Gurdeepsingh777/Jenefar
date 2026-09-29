class TextToSpeech:
    """Interface for a text-to-speech provider."""

    def speak(self, text: str) -> None:
        raise NotImplementedError
