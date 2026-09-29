class Microphone:
    """Interface for microphone backends."""

    def listen(self) -> str:
        raise NotImplementedError
