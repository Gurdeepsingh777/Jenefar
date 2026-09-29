class SpeechToText:
    """Interface for a speech-to-text provider."""

    def transcribe(self, audio) -> str:
        raise NotImplementedError
