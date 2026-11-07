"""Regression: dashboard tidak boleh membocorkan jadwal dan tidak boleh punya
admin default yang dapat diduga (audit 2026-11-07).

Sebelum perbaikan: GET /login merender kalender bulan penuh berisi nama anggota
dan status jadwal, dan `init_default_admin` membuat admin/admin123 otomatis.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db


def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "web.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    db.create_tables()
    db.init_default_settings()
    db.set_user_group(777, "Rahasia", "rahasia_user", "APPS")
    db.add_jadwal_manual(777, "Rahasia", "rahasia_user", "2026-11-10")
    return db_path


def _client():
    from web.app import create_app

    return create_app().test_client()


def test_login_page_does_not_expose_schedule(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    body = _client().get("/login").get_data(as_text=True)

    assert "Rahasia" not in body
    assert "rahasia_user" not in body
    assert "2026-11-10" not in body
    assert 'name="username"' in body, "form login harus tetap ada"


def test_no_default_admin_without_env(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.delenv("DEFAULT_ADMIN_PASSWORD", raising=False)

    db.init_default_admin()

    assert db.get_all_admin_users() == []


def test_default_admin_created_from_env(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "ganti-sekarang")

    db.init_default_admin()

    admins = db.get_all_admin_users()
    assert [admin["username"] for admin in admins] == ["admin"]
    assert db.verify_admin("admin", "ganti-sekarang") is not None


def test_login_rate_limited_after_five_failures(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "benar-sekali")
    db.init_default_admin()

    from web import app as web_app

    web_app.LOGIN_ATTEMPTS.clear()
    client = _client()
    for _ in range(5):
        client.post("/login", data={"username": "admin", "password": "salah"})

    body = client.post("/login", data={"username": "admin", "password": "benar-sekali"}).get_data(as_text=True)

    assert "Terlalu banyak percobaan" in body
    web_app.LOGIN_ATTEMPTS.clear()


def test_secret_key_is_stable_across_restarts(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    from web.app import _load_secret_key

    first = _load_secret_key()
    second = _load_secret_key()

    assert first == second
    assert len(first) >= 16


def test_web_host_defaults_to_localhost(tmp_path, monkeypatch):
    import importlib

    monkeypatch.delenv("WEB_HOST", raising=False)

    reloaded = importlib.reload(config)

    assert reloaded.WEB_HOST == "127.0.0.1"
    assert isinstance(reloaded.WEB_PORT, int)
