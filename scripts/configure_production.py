#!/usr/bin/env python3
"""Securely configure Jenefar's local production secrets/providers."""

from __future__ import annotations

import argparse
import getpass
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def read_env() -> list[str]:
    if not ENV_PATH.exists():
        example = ROOT / ".env.example"
        return example.read_text(encoding="utf-8").splitlines() if example.exists() else []
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def set_value(lines: list[str], key: str, value: str) -> list[str]:
    prefix = key + "="
    result: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith(prefix):
            if not replaced:
                result.append(prefix + value)
                replaced = True
        else:
            result.append(line)
    if not replaced:
        result.append(prefix + value)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["openai", "groq", "gemini", "openrouter", "cerebras"])
    parser.add_argument("--no-provider", action="store_true")
    parser.add_argument("--force-approval-secret", action="store_true")
    args = parser.parse_args()

    lines = read_env()
    current = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in lines
        if "=" in line and not line.lstrip().startswith("#")
    }

    approval = current.get("JENEFAR_APPROVAL_SECRET", "").strip()
    if args.force_approval_secret or not approval:
        approval = secrets.token_urlsafe(48)
        lines = set_value(lines, "JENEFAR_APPROVAL_SECRET", approval)
        print("[JENEFAR] Generated a new approval secret.")

    if args.provider and not args.no_provider:
        env_key = {
            "openai": "OPENAI_API_KEY",
            "groq": "GROQ_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "cerebras": "CEREBRAS_API_KEY",
        }[args.provider]
        value = getpass.getpass(f"Enter {env_key} (input hidden): ").strip()
        if not value:
            raise SystemExit("Provider key cannot be empty.")
        lines = set_value(lines, env_key, value)
        print(f"[JENEFAR] Configured {args.provider} provider key.")

    lines = set_value(lines, "JENEFAR_APPROVAL_SECRET", approval)
    ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    try:
        os.chmod(ENV_PATH, 0o600)
    except OSError:
        pass

    print(f"[JENEFAR] Secure configuration written to {ENV_PATH}")
    print("[JENEFAR] Secret values were not displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
