from __future__ import annotations

import re
from pathlib import Path


_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def audit_env_file(path: str | Path) -> list[str]:
    """Report duplicate and shell-unsafe .env assignments without printing values.

    dotenv files may contain valid values that are not shell syntax. The audit
    reports suspicious lines only; it never executes or rewrites them and never
    reveals secrets.
    """
    env_path = Path(path)
    if not env_path.is_file():
        return []

    assignments: dict[str, list[int]] = {}
    issues: list[str] = []

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [f"cannot read .env ({type(exc).__name__})"]

    for line_number, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        match = _ASSIGNMENT.match(raw_line)
        if not match:
            issues.append(
                f"line {line_number}: not a KEY=value assignment; check for stray text"
            )
            continue

        key, raw_value = match.group(1), match.group(2).strip()
        assignments.setdefault(key, []).append(line_number)

        if raw_value.startswith(("'", '"')):
            quote = raw_value[0]
            closing = next(
                (
                    index for index in range(1, len(raw_value))
                    if raw_value[index] == quote
                    and (index == 0 or raw_value[index - 1] != "\\")
                ),
                None,
            )
            if closing is None:
                issues.append(f"{key} line {line_number}: quote is not closed")
            else:
                suffix = raw_value[closing + 1 :].strip()
                if suffix and not suffix.startswith("#"):
                    issues.append(
                        f"{key} line {line_number}: unexpected text after quoted value"
                    )
            continue

        # Ignore a trailing shell comment when assessing whitespace.
        # Embedded spaces must be quoted for shell sourcing. Target lists use commas.
        value_without_comment = re.sub(r"\s+#.*$", "", raw_value).strip()
        if value_without_comment and re.search(r"\s", value_without_comment):
            hint = (
                "; use comma-separated targets inside quotes"
                if key == "JENEFAR_AUTHORIZED_TARGETS"
                else "; wrap the complete value in matching quotes"
            )
            issues.append(
                f"{key} line {line_number}: unquoted whitespace may break source .env{hint}"
            )

    for key, line_numbers in assignments.items():
        if len(line_numbers) > 1:
            lines_display = ", ".join(str(n) for n in line_numbers)
            issues.append(
                f"{key}: assigned more than once (lines {lines_display}); keep one authoritative entry"
            )

    return issues


__all__ = ["audit_env_file"]
