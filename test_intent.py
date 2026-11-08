"""Test router niat bot jadwal."""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core.intent import classify_intent


def test_classify_intent_examples():
    cases = {
        "bagaimana cara batal jadwal?": "help",
        "tolong input jadwal saya tanggal 4, 5, dan 10": "fill",
        "ganti jadwal saya tanggal 4, 5": "replace",
        "batal jadwal saya": "cancel",
        "cuti tanggal 4": "leave",
        "tukar jadwal dengan @budi": "swap",
        "siapa yang SOS besok?": "query",
    }
    for text, expected in cases.items():
        assert classify_intent(text) == expected, (text, classify_intent(text))
