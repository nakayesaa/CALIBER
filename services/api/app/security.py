"""Write authorization and bounded rate limiting for workflow mutations."""

from __future__ import annotations

import os
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import StrEnum

from fastapi import HTTPException, status


class WriteMode(StrEnum):
    LOCAL = "local"
    READ_ONLY = "read_only"
    BEARER = "bearer"


@dataclass(frozen=True)
class Principal:
    subject: str
    display_name: str


class WriteAuthorizer:
    def __init__(
        self,
        mode: WriteMode,
        actor: str,
        bearer_token: str | None = None,
    ) -> None:
        actor = actor.strip()
        if not 1 <= len(actor) <= 120:
            raise ValueError("CALIBER_WRITE_ACTOR must contain 1 to 120 characters")
        if mode == WriteMode.BEARER and (
            bearer_token is None or len(bearer_token) < 32
        ):
            raise ValueError(
                "CALIBER_WRITE_TOKEN must contain at least 32 characters in bearer mode"
            )
        self.mode = mode
        self.actor = actor
        self.bearer_token = bearer_token

    @classmethod
    def from_environment(cls) -> WriteAuthorizer:
        raw_mode = os.getenv("CALIBER_WRITE_MODE", WriteMode.LOCAL.value).strip().lower()
        try:
            mode = WriteMode(raw_mode)
        except ValueError as error:
            raise ValueError(
                "CALIBER_WRITE_MODE must be local, read_only, or bearer"
            ) from error
        return cls(
            mode=mode,
            actor=os.getenv("CALIBER_WRITE_ACTOR", "CALIBER Demo User"),
            bearer_token=os.getenv("CALIBER_WRITE_TOKEN"),
        )

    def authorize(self, authorization: str | None) -> Principal:
        if self.mode == WriteMode.READ_ONLY:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Workflow changes are disabled in read-only mode",
            )
        if self.mode == WriteMode.BEARER:
            scheme, _, credential = (authorization or "").partition(" ")
            valid = (
                scheme.lower() == "bearer"
                and bool(credential)
                and self.bearer_token is not None
                and secrets.compare_digest(credential, self.bearer_token)
            )
            if not valid:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Valid bearer credentials are required for workflow changes",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return Principal(subject=self.actor.casefold(), display_name=self.actor)


class FixedWindowRateLimiter:
    def __init__(self, maximum_requests: int, window_seconds: int) -> None:
        if maximum_requests < 1 or window_seconds < 1:
            raise ValueError("Rate-limit values must be positive")
        self.maximum_requests = maximum_requests
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @classmethod
    def from_environment(cls) -> FixedWindowRateLimiter:
        return cls(
            maximum_requests=int(os.getenv("CALIBER_RCA_RATE_LIMIT", "3")),
            window_seconds=int(os.getenv("CALIBER_RCA_RATE_WINDOW_SECONDS", "60")),
        )

    def enforce(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.maximum_requests:
                retry_after = max(1, int(self.window_seconds - (now - events[0])) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="RCA generation rate limit exceeded",
                    headers={"Retry-After": str(retry_after)},
                )
            events.append(now)
