"""Prioritas 3 audit: throttle per-akun, password >72 byte, enumerasi timing, logout POST."""
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db

ADMIN_PASSWORD = "rahasia123"


@pytest.fixture(autouse=True)
def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "login_hardening.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", ADMIN_PASSWORD)

    from web import app as web_app

    web_app.LOGIN_ATTEMPTS.clear()
    web_app.ACCOUNT_ATTEMPTS.clear()

    db.create_tables()
    db.init_default_admin()
    yield
    web_app.LOGIN_ATTEMPTS.clear()
    web_app.ACCOUNT_ATTEMPTS.clear()


def _client():
    from web.app import create_app

    return create_app().test_client()


# ---------------------------------------------------------------------------
# Throttle per akun (bukan hanya per IP)
# ---------------------------------------------------------------------------

def test_account_throttle_blocks_even_from_healthy_ip(monkeypatch):
    from web import app as web_app

    monkeypatch.setattr(web_app, "LOGIN_MAX_ATTEMPTS", 3)
    client = _client()
    for _ in range(3):
        client.post("/login", data={"username": "admin", "password": "salah"})

    # IP sehat (dibersihkan), tapi akun 'admin' sudah kena batas
    web_app.LOGIN_ATTEMPTS.clear()
    response = client.post("/login", data={"username": "admin", "password": ADMIN_PASSWORD})

    assert response.status_code == 429
    assert "Terlalu banyak percobaan" in response.get_data(as_text=True)


def test_successful_login_clears_account_counter():
    from web import app as web_app

    client = _client()
    client.post("/login", data={"username": "admin", "password": "salah"})
    assert web_app.ACCOUNT_ATTEMPTS.get("admin") is not None

    client.post("/login", data={"username": "admin", "password": ADMIN_PASSWORD})

    assert "admin" not in web_app.ACCOUNT_ATTEMPTS


def test_expired_attempt_entries_are_pruned():
    from web import app as web_app

    old = time.time() - web_app.LOGIN_WINDOW_SECONDS - 5
    web_app.LOGIN_ATTEMPTS["10.9.9.9"] = (99, old)
    web_app.ACCOUNT_ATTEMPTS["hantu"] = (99, old)

    blocked = web_app._attempts_blocked(web_app.LOGIN_ATTEMPTS, "10.9.9.9")

    assert blocked is False
    assert "10.9.9.9" not in web_app.LOGIN_ATTEMPTS, "entri kedaluwarsa harus dibuang"
    assert "hantu" in web_app.ACCOUNT_ATTEMPTS, "prune hanya untuk store yang diakses"


# ---------------------------------------------------------------------------
# Password panjang tidak boleh bikin error 500 / crash
# ---------------------------------------------------------------------------

def test_verify_admin_handles_very_long_password():
    assert db.verify_admin("admin", "x" * 500) is None


def test_verify_admin_unknown_user_returns_none():
    assert db.verify_admin("tidak-ada", "apa-saja") is None


def test_long_password_still_logs_in_when_prefix_matches():
    """Semua byte setelah 72 diabaikan bcrypt — perilaku standar, bukan crash."""
    db.update_admin_password("admin", "p" * 80)

    assert db.verify_admin("admin", "p" * 80) is not None
    assert db.verify_admin("admin", "p" * 72) is not None


def test_login_with_huge_password_returns_401_not_500():
    client = _client()

    response = client.post("/login", data={"username": "admin", "password": "x" * 500})

    assert response.status_code == 200
    assert "Username atau password salah" in response.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Panjang password minimum & logout POST
# ---------------------------------------------------------------------------

def test_new_password_min_length_is_enforced():
    from web.app import MIN_PASSWORD_LENGTH

    client = _client()
    client.post("/login", data={"username": "admin", "password": ADMIN_PASSWORD})

    body = client.post(
        "/password",
        data={"current_password": ADMIN_PASSWORD, "new_password": "pendek", "confirm_password": "pendek"},
        follow_redirects=True,
    ).get_data(as_text=True)

    assert f"Password minimal {MIN_PASSWORD_LENGTH} karakter" in body
    assert db.verify_admin("admin", "pendek") is None


def test_logout_requires_post():
    client = _client()
    client.post("/login", data={"username": "admin", "password": ADMIN_PASSWORD})

    assert client.get("/logout").status_code == 405

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
