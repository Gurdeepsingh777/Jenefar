from jenefar.agents.llm_agent import BaseLLMAgent


class KaliSecurityAgent(BaseLLMAgent):
    name = "kali"
    description = "Kali Linux security-tool discovery and authorized execution specialist"
    use_tools = True
    allow_action_tools = True
    model_env = "JENEFAR_KALI_MODEL"
    system_prompt = """You are Jenefar's Kali Linux security-tool specialist.
Use the curated Kali catalog and local tool broker for authorized defensive security,
labs, CTFs, vulnerability validation and penetration testing. Kali has many offensive
capabilities, so never bypass authorization scope, confirmation, or tool policy.
For network-impacting actions, require an authorized target and explicit tool approval.
Explain which tool/category you are using and distinguish discovery from execution."""
    keywords = (
        "kali", "nmap", "masscan", "amass", "subfinder", "gobuster", "ffuf",
        "burpsuite", "zaproxy", "sqlmap", "hydra", "hashcat", "john",
        "aircrack", "metasploit", "msfconsole", "msfvenom", "impacket",
        "responder", "bloodhound", "mimikatz", "linpeas", "winpeas",
        "wireshark", "tcpdump", "volatility", "foremost", "binwalk",
        "reconnaissance", "credential access", "privilege escalation",
        "lateral movement", "forensics",
    )

    def can_handle(self, text: str) -> bool:
        lowered = text.lower()
        return any(item in lowered for item in self.keywords)
