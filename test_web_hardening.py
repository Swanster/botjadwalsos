"""Prioritas 2 audit: proteksi CSRF, flag cookie sesi, dan pesan error web.

Sebelum perbaikan: semua POST dashboard menerima request tanpa verifikasi origin
(terbukti POST /members/add tanpa token diterima), cookie sesi tanpa SameSite
eksplisit, dan exception mentah ditampilkan ke admin lewat flash.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db

ADMIN_PASSWORD = "rahasia123"


@pytest.fixture(autouse=True)
def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "hardening.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", ADMIN_PASSWORD)
    db.create_tables()
    db.set_user_group(999, "Uji", "uji_tg", "APPS")
    yield


def _client(login=True):
    from web.app import create_app

    client = create_app().test_client()
    if login:
        assert client.post("/login", data={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 302
    return client


# ---------------------------------------------------------------------------
# CSRF: POST lintas origin ditolak, same-origin tetap jalan
# ---------------------------------------------------------------------------

def test_post_from_foreign_origin_is_rejected():
    client = _client()

    response = client.post(
        "/members/add",
        data={"user_id": "1234", "username": "Penyusup", "group_name": "APPS"},
        headers={"Origin": "https://jahat.example"},
    )

    assert response.status_code == 403
    assert db.get_user_group(1234) is None, "tidak boleh ada data tersimpan dari origin asing"


def test_post_from_same_origin_is_allowed():
    client = _client()

    response = client.post(
        "/members/add",
        data={"user_id": "1234", "username": "Budi", "group_name": "APPS"},
        headers={"Origin": "http://localhost"},
    )

    assert response.status_code == 302
    assert db.get_user_group(1234) == "APPS"


def test_foreign_referer_is_rejected_when_origin_absent():
    client = _client()

    response = client.post(
        "/settings",
        data={"kuota_apps": "9"},
        headers={"Referer": "https://jahat.example/form"},
    )

    assert response.status_code == 403


def test_post_without_origin_header_is_allowed_for_internal_scripts():
    """curl/script internal tidak mengirim Origin; cookie SameSite=Lax tetap menahan browser."""
    client = _client()

    response = client.post("/members/add", data={"user_id": "1234", "username": "Budi", "group_name": "APPS"})

    assert response.status_code == 302
    assert db.get_user_group(1234) == "APPS"


def test_get_is_not_affected_by_origin_check():
    client = _client()

    response = client.get("/members", headers={"Origin": "https://jahat.example"})

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Cookie sesi
# ---------------------------------------------------------------------------

def test_session_cookie_flags():
    from web.app import create_app

    app = create_app()

    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SECURE"] is False, "HTTP lokal: Secure harus off supaya login tetap jalan"


def test_login_sets_samesite_cookie():
    client = _client(login=False)

    response = client.post("/login", data={"username": "admin", "password": ADMIN_PASSWORD})

    cookie = response.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_secure_cookie_can_be_enabled_for_https(monkeypatch):
    monkeypatch.setenv("WEB_COOKIE_SECURE", "true")
    from web.app import create_app

    assert create_app().config["SESSION_COOKIE_SECURE"] is True


# ---------------------------------------------------------------------------
# Pesan error web tidak membocorkan detail internal
# ---------------------------------------------------------------------------

def test_schedule_error_message_is_generic(monkeypatch):
    from web import app as web_app

    def _boom(*args, **kwargs):
        raise RuntimeError("SQLITE_RAW_DETAIL_12345")

    monkeypatch.setattr(web_app, "add_jadwal_manual", _boom)
    client = _client()

    body = client.post(
        "/schedules/add",
        data={"user_id": "999", "tanggal": "2026-11-12"},
        follow_redirects=True,
    ).get_data(as_text=True)

    assert "SQLITE_RAW_DETAIL_12345" not in body
    assert "Terjadi kesalahan saat menyimpan jadwal" in body
