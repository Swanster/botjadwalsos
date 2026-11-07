"""Kontrak /tanya: LLM memakai konteks jadwal, gagal = fallback deterministik."""
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import ai_query, database as db


def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "ai.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    db.create_tables()
    db.set_user_group(1, "Budi", "budi", "INFRA_OPERATION")
    db.set_user_group(2, "Sari", "sari", "APPS")
    db.add_jadwal_manual(1, "Budi", "budi", "2026-11-08")


def test_llm_menerima_konteks_jadwal(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "AI_BASE_URL", "http://llm.local/v1")
    monkeypatch.setattr(config, "AI_API_KEY", "test-key")
    seen = {}

    def fake_post(payload):
        seen["payload"] = payload
        return {"choices": [{"message": {"content": "Besok: Budi."}}]}

    monkeypatch.setattr(ai_query, "_post_chat", fake_post)
    result = ai_query.answer("siapa yang SOS besok?", today=date(2026, 11, 7))

    assert result == "Besok: Budi."
    prompt = seen["payload"]["messages"][1]["content"]
    assert "2026-11-08" in prompt
    assert "Budi" in prompt
    assert "TOLAK" in seen["payload"]["messages"][0]["content"]


def test_gagal_llm_jatuh_ke_parser_deterministik(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "AI_BASE_URL", "http://llm.local/v1")
    monkeypatch.setattr(config, "AI_API_KEY", "test-key")

    def fake_post(payload):
        raise RuntimeError("gateway down")

    monkeypatch.setattr(ai_query, "_post_chat", fake_post)
    result = ai_query.answer("siapa yang SOS besok?", today=date(2026, 11, 7))

    assert "Budi" in result
    assert "8 November 2026" in result


def test_tanpa_konfigurasi_tidak_memanggil_llm(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "AI_BASE_URL", "")
    monkeypatch.setattr(config, "AI_API_KEY", "")
    monkeypatch.setattr(ai_query, "_post_chat", lambda payload: (_ for _ in ()).throw(AssertionError("dipanggil")))

    result = ai_query.answer("siapa yang SOS besok?", today=date(2026, 11, 7))

    assert "Budi" in result


def test_pertanyaan_politik_tidak_dikirim_ke_llm(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "AI_BASE_URL", "http://llm.local/v1")
    monkeypatch.setattr(config, "AI_API_KEY", "test-key")
    monkeypatch.setattr(ai_query, "_post_chat", lambda payload: (_ for _ in ()).throw(AssertionError("dipanggil")))

    result = ai_query.answer("siapa presiden Indonesia?", today=date(2026, 11, 7))

    assert result == ai_query.REFUSAL_MSG


def test_pertanyaan_umum_aman_dijawab_llm_tanpa_konteks_jadwal(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "AI_BASE_URL", "http://llm.local/v1")
    monkeypatch.setattr(config, "AI_API_KEY", "test-key")
    seen = {}

    def fake_post(payload):
        seen["payload"] = payload
        return {"choices": [{"message": {"content": "Fotosintesis adalah proses tumbuhan membuat makanan."}}]}

    monkeypatch.setattr(ai_query, "_post_chat", fake_post)
    result = ai_query.answer("apa itu fotosintesis?", today=date(2026, 11, 7))

    assert "Fotosintesis" in result
    assert "Jadwal SOS 30 hari" not in seen["payload"]["messages"][1]["content"]


def test_detail_internal_program_ditolak_tanpa_llm(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "AI_BASE_URL", "http://llm.local/v1")
    monkeypatch.setattr(config, "AI_API_KEY", "test-key")
    monkeypatch.setattr(ai_query, "_post_chat", lambda payload: (_ for _ in ()).throw(AssertionError("dipanggil")))

    result = ai_query.answer("jelaskan kode sumber bot ini secara mendalam", today=date(2026, 11, 7))

    assert result == ai_query.INTERNAL_MSG


def test_frasa_aman_sara_tidak_ikut_diblokir():
    assert ai_query.is_blocked_topic("jelaskan suku cadang motor") is False
    assert ai_query.is_blocked_topic("jelaskan suku bangsa di Indonesia") is True


def test_parse_sse_menggabungkan_delta():
    text = (
        'data: {"choices":[{"delta":{"content":"Halo "}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"dunia"}}]}\n\n'
        'data: [DONE]\n\n'
    )
    assert ai_query._parse_sse(text)["choices"][0]["message"]["content"] == "Halo dunia"