from __future__ import annotations

from jenefar.core.env_diagnostics import audit_env_file


def test_audit_detects_duplicate_provider_order_without_showing_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "JENEFAR_PROVIDER_ORDER=gemini,openrouter\n"
        "JENEFAR_PROVIDER_ORDER=oxion,openai,gemini\n",
        encoding="utf-8",
    )

    issues = audit_env_file(env_file)

    assert len(issues) == 1
    assert "JENEFAR_PROVIDER_ORDER" in issues[0]
    assert "lines 1, 2" in issues[0]
    assert "gemini,openrouter" not in str(issues)


def test_audit_detects_unquoted_space_in_authorized_targets(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        'JENEFAR_AUTHORIZED_TARGETS=192.168.29.0/24 172.16.1.10\n',
        encoding="utf-8",
    )

    issues = audit_env_file(env_file)

    assert len(issues) == 1
    assert "JENEFAR_AUTHORIZED_TARGETS line 1" in issues[0]
    assert "comma-separated targets inside quotes" in issues[0]


def test_audit_accepts_quoted_values_and_shell_comments(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        'JENEFAR_WAKE_PHRASES="Hi Jenefar,Hello Jenefar"\n'
        'JENEFAR_BROWSER_TTS_INSTRUCTIONS="natural female voice" # valid comment\n'
        'OXION_MODEL=gpt-5.6-luna # default model\n',
        encoding="utf-8",
    )

    assert audit_env_file(env_file) == []


def test_audit_detects_unclosed_quote_and_standalone_text(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        'JENEFAR_BROWSER_TTS_INSTRUCTIONS="natural female voice\n'
        '172.16.1.10\n',
        encoding="utf-8",
    )

    issues = audit_env_file(env_file)

    assert any("quote is not closed" in issue for issue in issues)
    assert any("line 2: not a KEY=value assignment" in issue for issue in issues)
