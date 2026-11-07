"""Halaman publik jadwal ("siapa yang SOS") harus tetap terbuka tanpa login,
tapi hanya memuat nama + divisi — bukan data sensitif dashboard.

Keputusan owner (2026-11-07): roster boleh dilihat siapa pun yang punya link.
Batasan yang dikunci di sini: /login tetap bersih, dan halaman publik tidak
membocorkan username Telegram, menu admin, atau form login apa pun.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db

MEMBER_ID = 777
MEMBER_NAME = "Budi Standby"
MEMBER_TG = "budi_telegram_rahasia"


@pytest.fixture(autouse=True)
def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "public.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "rahasia123")

    db.create_tables()
    db.set_user_group(MEMBER_ID, MEMBER_NAME, MEMBER_TG, "APPS")
    db.add_jadwal_manual(MEMBER_ID, MEMBER_NAME, MEMBER_TG, "2026-11-10")
    yield


def _client():
    from web.app import create_app

    return create_app().test_client()


def _html(response):
    return response.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Terbuka tanpa login
# ---------------------------------------------------------------------------

def test_root_renders_public_schedule_without_login():
    body = _html(_client().get("/"))

    assert "Varnion SOS" in body
    assert "Masuk Admin" in body


def test_public_page_shows_name_for_requested_month():
    body = _html(_client().get("/jadwal?year=2026&month=11"))

    assert MEMBER_NAME in body
    assert "November 2026" in body


def test_public_page_filters_other_months():
    body = _html(_client().get("/jadwal?year=2026&month=12"))

    assert MEMBER_NAME not in body
    assert "Desember 2026" in body


def test_invalid_month_falls_back_to_current_month():
    response = _client().get("/jadwal?year=2026&month=99")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tidak membocorkan data sensitif
# ---------------------------------------------------------------------------

def test_public_page_hides_telegram_username_and_admin_menu():
    body = _html(_client().get("/jadwal?year=2026&month=11"))

    assert MEMBER_TG not in body, "username Telegram tidak boleh tampil di halaman publik"
    for label in ("Log Aktivitas", "User Akses", "Ganti Password", "Batasan Harian"):
        assert label not in body, f"menu admin '{label}' bocor ke halaman publik"


def test_login_page_still_has_no_schedule():
    body = _html(_client().get("/login"))

    assert MEMBER_NAME not in body
    assert 'name="username"' in body


# ---------------------------------------------------------------------------
# Halaman privat tetap butuh login, admin tetap diarahkan ke dashboard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/dashboard", "/members", "/schedules", "/admins"])
def test_private_pages_still_require_login(path):
    response = _client().get(path)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_authenticated_root_redirects_to_dashboard():
    client = _client()
    client.post("/login", data={"username": "admin", "password": "rahasia123"})

    response = client.get("/")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")
