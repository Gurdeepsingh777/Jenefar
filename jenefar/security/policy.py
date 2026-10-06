from __future__ import annotations
import hashlib, hmac, ipaddress, json, os, re, secrets, threading, time
from pathlib import Path
from urllib.parse import urlparse

SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
)

def redact(value: object, replacement: str = "[REDACTED]") -> str:
    text = str(value)
    for pattern in SECRET_PATTERNS:
        def replace(match):
            if match.lastindex and match.lastindex >= 2 and "=" in match.group(0):
                return f"{match.group(1)}={replacement}"
            return replacement
        text = pattern.sub(replace, text)
    return text

def safe_path(path: str | Path, roots: list[str | Path]) -> Path:
    target = Path(path).expanduser().resolve()
    allowed = [Path(r).expanduser().resolve() for r in roots]
    if not any(target == root or root in target.parents for root in allowed):
        raise PermissionError(f"path outside authorized workspace: {target}")
    return target

def validate_url(url: str, *, allow_http: bool = True, allow_private: bool = False) -> str:
    parsed = urlparse(str(url).strip())
    schemes = ("http", "https") if allow_http else ("https",)
    if parsed.scheme not in schemes or not parsed.hostname:
        raise ValueError("unsupported or malformed URL")
    host = parsed.hostname
    try:
        addr = ipaddress.ip_address(host)
        if not allow_private and (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved):
            raise PermissionError("private/loopback URL blocked")
    except ValueError:
        lowered = host.lower().rstrip(".")
        if lowered == "localhost" or lowered.endswith(".localhost"):
            raise PermissionError("local hostname blocked")
    return parsed.geturl()

class ApprovalManager:
    def __init__(self, secret: str | None = None, ttl_seconds: int = 300):
        self.secret = (secret or os.getenv("JENEFAR_APPROVAL_SECRET") or secrets.token_hex(32)).encode()
        self.ttl = max(10, min(int(ttl_seconds), 3600))
    def issue(self, action: str, task_id: str) -> str:
        expiry = int(time.time()) + self.ttl
        body = f"{task_id}|{action}|{expiry}"
        sig = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
        return f"{body}|{sig}"
    def verify(self, token: str, action: str, task_id: str) -> bool:
        try:
            tid, act, expiry, sig = token.split("|", 3)
            body = f"{tid}|{act}|{expiry}"
            expected = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
            return tid == task_id and act == action and int(expiry) >= int(time.time()) and hmac.compare_digest(sig, expected)
        except (ValueError, TypeError):
            return False

class AuditChain:
    def __init__(self, path: str | Path = "data/security_audit.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
    def append(self, event: dict[str, object]) -> str:
        with self._lock:
            previous = ""
            if self.path.exists():
                try:
                    lines = self.path.read_text(encoding="utf-8").splitlines()
                    if lines:
                        previous = json.loads(lines[-1]).get("hash", "")
                except (OSError, IndexError, json.JSONDecodeError):
                    previous = ""
            payload = {key: redact(value) if key in {"event", "error"} else value for key, value in dict(event).items()}
            payload["previous_hash"] = previous
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
            digest = hashlib.sha256(canonical.encode()).hexdigest()
            payload["hash"] = digest
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
            return digest
