from __future__ import annotations
import json, os, sys
from urllib.request import urlopen

base=f"http://{os.getenv('JENEFAR_HOST','127.0.0.1')}:{os.getenv('JENEFAR_AVATAR_PORT','8787')}"
checks={}
for name,path in {"health":"/health","runtime":"/runtime/status","readiness":"/production/readiness"}.items():
    try:
        with urlopen(base+path, timeout=3) as response:
            checks[name] = response.status == 200
    except Exception as exc:
        checks[name] = False
        print(f"{name}: {type(exc).__name__}: {exc}", file=sys.stderr)
print(json.dumps(checks, sort_keys=True))
raise SystemExit(0 if all(checks.values()) else 1)
