"""Opt-in, same-origin demo authentication. Account files stay outside source control.

password_hash: {algorithm: "pbkdf2_sha256", iterations: 600000,
                salt: "random salt string", hash: "hex SHA256 derived key"}
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

COOKIE = "__Host-iris-session"
TTL = 8 * 60 * 60


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)


def _version(account: dict) -> str:
    return hashlib.sha256(json.dumps(account, sort_keys=True).encode()).hexdigest()


def _accounts(path: Path) -> dict:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("Account file must contain an object")
    for username, account in data.items():
        password = account["password_hash"]
        if (
            not isinstance(username, str)
            or not isinstance(account["person_id"], str)
            or not account["person_id"]
            or password["algorithm"] != "pbkdf2_sha256"
            or not isinstance(password["iterations"], int)
            or not 600000 <= password["iterations"] <= 2000000
            or not isinstance(password["salt"], str)
            or not password["salt"]
            or len(bytes.fromhex(password["hash"])) != 32
        ):
            raise ValueError("Invalid demo account configuration")
    return data


def install_demo_auth(app: FastAPI) -> None:
    """Install only on the explicitly configured competition server."""
    secret_file = os.environ.get("IRIS_SESSION_SECRET_FILE")
    secret = (
        Path(secret_file).read_text().strip()
        if secret_file
        else os.environ.get("IRIS_SESSION_SECRET", "")
    ).encode()
    if len(secret) < 32:
        raise ValueError("IRIS_SESSION_SECRET must contain at least 32 bytes")
    path = Path(os.environ["IRIS_DEMO_ACCOUNTS_FILE"])
    _accounts(path)  # fail closed at startup for invalid configuration
    attempts: OrderedDict[str, list[float]] = OrderedDict()
    lock = threading.Lock()
    mutations = asyncio.Lock()

    def sign(payload: dict) -> str:
        body = (
            base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
            .decode()
            .rstrip("=")
        )
        signature = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        return body + "." + signature

    def identity(request: Request) -> dict | None:
        token = request.cookies.get(COOKIE, "")
        if len(token) > 4096:
            return None
        try:
            body, signature = token.split(".")
            expected = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return None
            payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            account = _accounts(path).get(payload["username"])
            now = time.time()
            if (
                account is None
                or not now < payload["exp"] <= now + TTL
                or payload["version"] != _version(account)
            ):
                return None
            return {"username": payload["username"], "person_id": account["person_id"]}
        except (ValueError, KeyError, TypeError, OSError):
            return None

    class Authentication(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            route = request.url.path
            protected = route.startswith("/api/") or route in ("/auth/session", "/auth/logout")
            if (protected or route == "/auth/login") and request.method not in (
                "GET",
                "HEAD",
                "OPTIONS",
            ):
                origin = request.headers.get("origin")
                expected = (
                    os.environ.get("IRIS_PUBLIC_ORIGIN")
                    or os.environ.get("RENDER_EXTERNAL_URL")
                    or f"{request.url.scheme}://{request.url.netloc}"
                )
                if origin != expected:
                    return JSONResponse({"detail": "Same-origin request required"}, status_code=403)
            if protected:
                person = identity(request)
                if person is None:
                    return JSONResponse({"detail": "Authentication required"}, status_code=401)
                supplied = request.headers.getlist("x-caliber-person")
                if any(value != person["person_id"] for value in supplied):
                    return JSONResponse({"detail": "Identity header mismatch"}, status_code=403)
                request.scope["headers"] = [
                    (k, v) for k, v in request.scope["headers"] if k.lower() != b"x-caliber-person"
                ] + [(b"x-caliber-person", person["person_id"].encode())]
                request.state.demo_identity = person
            if protected and request.method not in ("GET", "HEAD", "OPTIONS"):
                async with mutations:
                    response = await call_next(request)
            else:
                response = await call_next(request)
            if protected:
                response.headers["Cache-Control"] = "no-store"
            if route == "/api/v1/workflow/session" and response.status_code == 200:
                body = b"".join([part async for part in response.body_iterator])
                data = json.loads(body)
                data["can_switch"] = False
                headers = dict(response.headers)
                headers.pop("content-length", None)
                return JSONResponse(data, status_code=response.status_code, headers=headers)
            return response

    app.add_middleware(Authentication)

    @app.post("/auth/login")
    def login(body: Login, request: Request):
        client_host = request.client.host if request.client else "unknown"
        key = client_host + ":" + body.username
        now = time.monotonic()
        with lock:
            for old_key in list(attempts):
                if not attempts[old_key] or attempts[old_key][-1] <= now - 300:
                    del attempts[old_key]
            events = [event for event in attempts.get(key, []) if event > now - 300]
            if len(events) >= 5 or (key not in attempts and len(attempts) >= 10000):
                return JSONResponse(
                    {"detail": "Too many login attempts"},
                    status_code=429,
                    headers={"Retry-After": "300"},
                )
            events.append(now)
            attempts[key] = events
        account = _accounts(path).get(body.username)
        password = (
            account["password_hash"]
            if account
            else {"salt": "iris-missing-account", "iterations": 600000, "hash": "0" * 64}
        )
        derived = hashlib.pbkdf2_hmac(
            "sha256", body.password.encode(), password["salt"].encode(), password["iterations"]
        ).hex()
        if not hmac.compare_digest(derived, password["hash"]) or account is None:
            return JSONResponse({"detail": "Invalid credentials"}, status_code=401)
        with lock:
            attempts.pop(key, None)
        response = JSONResponse({"username": body.username, "person_id": account["person_id"]})
        response.headers["Cache-Control"] = "no-store"
        response.set_cookie(
            COOKIE,
            sign(
                {
                    "username": body.username,
                    "version": _version(account),
                    "exp": int(time.time()) + TTL,
                }
            ),
            max_age=TTL,
            httponly=True,
            secure=True,
            samesite="strict",
            path="/",
        )
        return response

    @app.get("/auth/session")
    def session(request: Request):
        return JSONResponse(request.state.demo_identity, headers={"Cache-Control": "no-store"})

    @app.post("/auth/logout")
    def logout():
        response = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
        response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
        return response
