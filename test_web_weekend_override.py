#!/usr/bin/env python3
"""Verify web app admin can add users to weekend dates freely (bypass quota/balance),
but rejects exact duplicate (same user + same date).

Uses Flask test client + a temp DB copy so we never touch prod data.
"""
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta

import pytz

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db

_TMP = tempfile.mkdtemp(prefix="jadwal_test_")
SRC_DB = os.path.join(ROOT, "data", "jadwal_pro.db")
DST_DB = os.path.join(_TMP, "jadwal_pro.db")
shutil.copyfile(SRC_DB, DST_DB)
config.DB_NAME = DST_DB
db.create_tables()
db.init_default_admin()

from web.app import create_app

MAKASSAR = pytz.timezone("Asia/Makassar")


def _next_weekend():
    today = datetime.now(MAKASSAR).date()
    off_sat = (5 - today.weekday()) % 7 or 7
    off_sun = (6 - today.weekday()) % 7 or 7
    sat = today + timedelta(days=off_sat)
    sun = today + timedelta(days=off_sun)
    return sat, sun


def main():
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()

    user = os.environ.get("TEST_ADMIN_USER", "admin")
    pw = os.environ.get("TEST_ADMIN_PW", "admin123")
    r = client.post("/login", data={"username": user, "password": pw},
                    follow_redirects=False)
    print("login status:", r.status_code)
    assert r.status_code in (302, 200)

    sat, sun = _next_weekend()
    sat_str = sat.strftime("%Y-%m-%d")
    sun_str = sun.strftime("%Y-%m-%d")

    members = db.get_all_users_in_group("INFRA") + db.get_all_users_in_group("APPS") + db.get_all_users_in_group("MONITORING")
    assert len(members) >= 2, "need >=2 members to test"
    u1 = dict(members[0])
    u2 = dict(members[1])
    print("u1:", u1["username"], u1["user_id"], "| u2:", u2["username"], u2["user_id"])
    print("weekend:", sat_str, sun_str)

    # (A) same user on Saturday AND Sunday -> should be 2 rows
    r1 = client.post("/schedules/add", data={"user_id": str(u1["user_id"]), "tanggal": sat_str}, follow_redirects=False)
    r2 = client.post("/schedules/add", data={"user_id": str(u1["user_id"]), "tanggal": sun_str}, follow_redirects=False)
    print("A) same user Sat+Sun statuses:", r1.status_code, r2.status_code)

    # (B) different user on same Saturday -> should succeed (daily limit bypassed)
    r3 = client.post("/schedules/add", data={"user_id": str(u2["user_id"]), "tanggal": sat_str}, follow_redirects=False)
    print("B) different user same Sat status:", r3.status_code)

    # (C) same user same Saturday AGAIN -> should be rejected (duplicate)
    r4 = client.post("/schedules/add", data={"user_id": str(u1["user_id"]), "tanggal": sat_str}, follow_redirects=False)
    print("C) same user same Sat again status:", r4.status_code)

    # Verify DB state
    rows_u1 = db.get_user_jadwal_for_month(u1["user_id"], sat.year, sat.month)
    sat_u1 = [x for x in rows_u1 if x["tanggal"] == sat_str]
    sun_u1 = [x for x in rows_u1 if x["tanggal"] == sun_str]
    rows_u2 = db.get_user_jadwal_for_month(u2["user_id"], sat.year, sat.month)
    sat_u2 = [x for x in rows_u2 if x["tanggal"] == sat_str]

    print(f"DB: u1 on Sat={len(sat_u1)} (expect 1), u1 on Sun={len(sun_u1)} (expect 1), u2 on Sat={len(sat_u2)} (expect 1)")
    assert len(sat_u1) == 1, f"u1 Sat dup not prevented: {len(sat_u1)}"
    assert len(sun_u1) == 1, f"u1 Sun missing: {len(sun_u1)}"
    assert len(sat_u2) == 1, f"u2 Sat missing (daily limit not bypassed): {len(sat_u2)}"

    print("RESULT: weekend override OK — admin can fill user >1x across weekend days & multiple users per weekend day; duplicates prevented.")
    shutil.rmtree(_TMP, ignore_errors=True)
    print("PASS")


if __name__ == "__main__":
    main()
