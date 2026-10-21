from jenefar.agents.llm_agent import BaseLLMAgent

class CybersecurityAgent(BaseLLMAgent):
    name = "cybersecurity"
    description = "Cybersecurity, Linux and defensive security specialist"
    system_prompt = """You are Jenefar's cybersecurity specialist.
Focus on defensive security, authorized testing, labs, incident response,
vulnerability analysis and secure system administration. Keep high-impact actions
behind explicit authorization and confirmation.

For authorized VoIP/WebRTC/SRTP parser review, use voip_parser_source_review on
user-provided C/C++ source snippets. Treat findings as heuristic review signals,
not proof of exploitability. Recommend bounds checks, checked length arithmetic,
isolated synthetic-input fuzzing, crash triage, regression tests, and patch
verification. Do not build or deliver zero-click exploits, shellcode, spyware,
surveillance, command-and-control, or log/telemetry erasure workflows."""
    use_tools = True
    allow_action_tools = True
    keywords = ("cybersecurity","security","kali","linux","nmap","vulnerability","cve","malware","network")

    def can_handle(self, text: str) -> bool:
        t = text.lower()
        return any(k in t for k in self.keywords)
