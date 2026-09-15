"""Security boundary tests independent of generated case artifacts."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.api.app.security import (
    FixedWindowRateLimiter,
    WriteAuthorizer,
    WriteMode,
)


def test_local_authorizer_uses_configured_trusted_identity() -> None:
    principal = WriteAuthorizer(WriteMode.LOCAL, "Reliability Engineer").authorize(None)
    assert principal.subject == "reliability engineer"
    assert principal.display_name == "Reliability Engineer"


def test_bearer_authorizer_requires_constant_server_credential() -> None:
    token = "a-secure-test-token-with-32-characters"
    authorizer = WriteAuthorizer(WriteMode.BEARER, "Workflow Reviewer", token)

    with pytest.raises(HTTPException) as missing:
        authorizer.authorize(None)
    with pytest.raises(HTTPException) as invalid:
        authorizer.authorize("Bearer wrong-token")

    assert missing.value.status_code == 401
    assert invalid.value.status_code == 401
    assert authorizer.authorize(f"Bearer {token}").display_name == "Workflow Reviewer"


def test_bearer_authorizer_rejects_short_server_secret() -> None:
    with pytest.raises(ValueError, match="at least 32 characters"):
        WriteAuthorizer(WriteMode.BEARER, "Workflow Reviewer", "too-short")


def test_rate_limiter_enforces_bounded_generation_window() -> None:
    limiter = FixedWindowRateLimiter(maximum_requests=2, window_seconds=60)
    limiter.enforce("reviewer")
    limiter.enforce("reviewer")

    with pytest.raises(HTTPException) as exceeded:
        limiter.enforce("reviewer")

    assert exceeded.value.status_code == 429
    assert int(exceeded.value.headers["Retry-After"]) >= 1
