from __future__ import annotations
from pathlib import Path
import os

REQUIRED = (
    "JENEFAR_TASK_HISTORY_PATH",
    "JENEFAR_LOCAL_LLM_BASE_URL",
)

def check() -> dict:
    warnings=[]; failures=[]
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("GROQ_API_KEY") and not os.getenv("JENEFAR_LOCAL_LLM_BASE_URL"):
        failures.append("no online or local LLM provider configured")
    if not Path("data").exists(): warnings.append("data directory missing; it will be created on first persistence")
    if os.getenv("JENEFAR_APPROVAL_SECRET") in (None,""): warnings.append("approval secret not explicitly configured; process-local secret will be generated")
    return {"ready":not failures,"failures":failures,"warnings":warnings}
