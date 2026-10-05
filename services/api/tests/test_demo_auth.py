import hashlib
import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    accounts = tmp_path / "accounts.json"
    record = {
        "person_id": "operator-1",
        "password_hash": {
            "algorithm": "pbkdf2_sha256",
            "iterations": 600000,
            "salt": "test-salt",
            "hash": hashlib.pbkdf2_hmac("sha256", b"good-password", b"test-salt", 600000).hex(),
        },
    }
    accounts.write_text(json.dumps({"alice": record}))
    monkeypatch.setenv("IRIS_DEMO_ACCOUNTS_FILE", str(accounts))
    monkeypatch.setenv("IRIS_SESSION_SECRET", "a" * 64)
    app = FastAPI()

    @app.get("/api/v1/who")
    def who(request: Request):
        return {"person_id": request.headers.get("X-Caliber-Person")}

    @app.post("/api/v1/write")
    def write():
        return {"ok": True}

    @app.get("/api/v1/workflow/session")
    def workflow():
        return {"can_switch": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    from app.demo_auth import install_demo_auth

    install_demo_auth(app)
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client, accounts, record


def login(client):
    return client.post(
        "/auth/login",
        json={"username": "alice", "password": "good-password"},
        headers={"origin": "https://testserver"},
    )


def test_auth_identity_and_cookie(client):
    c, _, _ = client
    assert c.get("/api/v1/who").status_code == 401
    assert c.get("/health").status_code == 200
    response = login(c)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
    assert c.get("/auth/session").json() == {"username": "alice", "person_id": "operator-1"}
    assert c.get("/api/v1/who").json()["person_id"] == "operator-1"
    assert c.get("/api/v1/who", headers={"X-Caliber-Person": "admin"}).status_code == 403
    assert c.get("/api/v1/workflow/session").json()["can_switch"] is False


def test_csrf_logout_and_invalid_credentials(client):
    c, _, _ = client
    assert (
        c.post(
            "/auth/login",
            json={"username": "alice", "password": "bad"},
            headers={"origin": "https://testserver"},
        ).status_code
        == 401
    )
    assert login(c).status_code == 200
    assert c.post("/api/v1/write").status_code == 403
    assert c.post("/api/v1/write", headers={"origin": "https://evil.test"}).status_code == 403
    assert c.post("/api/v1/write", headers={"origin": "https://testserver"}).status_code == 200
    assert c.post("/auth/logout", headers={"origin": "https://testserver"}).status_code == 200
    assert c.get("/auth/session").status_code == 401


def test_expiration_and_account_invalidation(client, monkeypatch):
    c, accounts, record = client
    assert login(c).status_code == 200
    import app.demo_auth as auth

    now = auth.time.time()
    monkeypatch.setattr(auth.time, "time", lambda: now + 28801)
    assert c.get("/auth/session").status_code == 401
    monkeypatch.setattr(auth.time, "time", lambda: now)
    assert login(c).status_code == 200
    record["password_hash"]["salt"] = "changed"
    accounts.write_text(json.dumps({"alice": record}))
    assert c.get("/auth/session").status_code == 401


def test_rate_limit(client):
    c, _, _ = client
    for _ in range(5):
        assert (
            c.post(
                "/auth/login",
                json={"username": "alice", "password": "bad"},
                headers={"origin": "https://testserver"},
            ).status_code
            == 401
        )
    assert login(c).status_code == 429


def test_tampering_csrf_and_removed_account(client):
    c, accounts, _ = client
    assert (
        c.post("/auth/login", json={"username": "alice", "password": "good-password"}).status_code
        == 403
    )
    assert login(c).status_code == 200
    original = c.cookies.get("__Host-iris-session")
    c.cookies.set(
        "__Host-iris-session",
        original[:-1] + ("0" if original[-1] != "0" else "1"),
        domain="testserver.local",
        path="/",
    )
    assert c.get("/auth/session").status_code == 401
    c.cookies.clear()
    assert login(c).status_code == 200
    accounts.write_text("{}")
    assert c.get("/auth/session").status_code == 401


def test_requires_secret(monkeypatch):
    from app.demo_auth import install_demo_auth

    monkeypatch.delenv("IRIS_SESSION_SECRET", raising=False)
    with pytest.raises(ValueError, match="IRIS_SESSION_SECRET"):
        install_demo_auth(FastAPI())


def test_proxy_origin_and_separate_account_limits(client, monkeypatch):
    c, _, _ = client
    monkeypatch.setenv("IRIS_PUBLIC_ORIGIN", "https://iris.example.com")
    # Simulate HTTP upstream behind an HTTPS edge. Origin follows the public URL.
    with TestClient(c.app, base_url="http://internal") as upstream:
        response = upstream.post(
            "/auth/login",
            json={"username": "alice", "password": "good-password"},
            headers={"origin": "https://iris.example.com"},
        )
        assert response.status_code == 200
        assert (
            upstream.post(
                "/auth/login",
                json={"username": "alice", "password": "good-password"},
                headers={"origin": "http://internal"},
            ).status_code
            == 403
        )
    monkeypatch.delenv("IRIS_PUBLIC_ORIGIN")
    for _ in range(5):
        assert (
            c.post(
                "/auth/login",
                json={"username": "other", "password": "bad"},
                headers={"origin": "https://testserver"},
            ).status_code
            == 401
        )
    assert login(c).status_code == 200
