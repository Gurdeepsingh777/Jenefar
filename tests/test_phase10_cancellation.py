import time

import pytest

from jenefar.core.cancellation import CancellationToken
from jenefar.core.llm import LLMClient


def test_cancellation_token_is_idempotent():
    token = CancellationToken()
    assert token.cancel() is True
    assert token.cancel() is False
    assert token.cancelled is True
    with pytest.raises(TimeoutError, match="execution cancelled"):
        token.raise_if_cancelled()


def test_llm_rejects_cancelled_token_before_provider_call():
    token = CancellationToken()
    token.cancel("test")
    client = LLMClient()
    with pytest.raises(TimeoutError, match="execution cancelled"):
        client.complete("hello", cancel_token=token)


def test_llm_remaining_timeout_still_works_with_future_deadline():
    deadline = time.monotonic() + 2
    assert 1.0 < LLMClient._remaining_timeout(deadline) <= 2.0