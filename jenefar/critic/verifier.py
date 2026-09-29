class Verifier:
    def verify(self, task: str, result: str) -> str:
        if not result or not result.strip():
            return "No usable result was produced."
        return result