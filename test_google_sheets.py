#!/usr/bin/env python3
"""
Test script untuk Google Sheets integration.
Jalankan ini setelah setup Google Cloud Console selesai.
"""

import sys
import os

# Tambahkan parent directory ke path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.google_sheets import get_google_sheets_client, sync_jadwal_to_sheets, sync_absensi_to_sheets, log_audit_to_sheets


def test_connection():
    """Test koneksi ke Google Sheets."""
    print("=" * 60)
    print("🧪 Testing Google Sheets Connection")
    print("=" * 60)

    client = get_google_sheets_client()

    if not client.is_enabled():
        print("\n❌ Google Sheets sync TIDAK aktif!")
        print("\nKemungkinan penyebab:")
        print("  1. File google_credentials.json belum ada")
        print("  2. GOOGLE_SHEET_ID belum diisi di config.py")
        print("  3. GOOGLE_SHEET_SYNC_ENABLED masih False")
        print("  4. Library gspread/google-auth belum terinstall")
        print("\nSolusi:")
        print("  → Ikuti panduan di GOOGLE_SHEETS_SETUP.md")
        return False

    print("\n✅ Google Sheets sync AKTIF!")

    # Test get sheet URL
    url = client.get_sheet_url()
    print(f"\n📊 Spreadsheet URL: {url}")

    return True


def test_write_jadwal():
    """Test write data jadwal."""
    print("\n" + "=" * 60)
    print("📝 Test Write: Jadwal")
    print("=" * 60)

    client = get_google_sheets_client()

    if not client.is_enabled():
        print("⚠️  Skip - Google Sheets tidak aktif")
        return False

    try:
        success = client.add_jadwal_entry(
            tanggal='2026-04-01',
            hari='Rabu',
            username='@test_user',
            user_id=123456789,
            group='INFRA',
            created_at='2026-03-31 10:00:00'
        )

        if success:
            print("✅ Test write jadwal BERHASIL!")
            print("   Cek Google Sheets tab 'Jadwal' untuk data test")
            return True
        else:
            print("❌ Test write jadwal GAGAL!")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_write_absensi():
    """Test write data absensi."""
    print("\n" + "=" * 60)
    print("📝 Test Write: Absensi")
    print("=" * 60)

    client = get_google_sheets_client()

    if not client.is_enabled():
        print("⚠️  Skip - Google Sheets tidak aktif")
        return False

    try:
        success = client.add_absensi_entry(
            tanggal='2026-04-02',
            username='@test_user',
            user_id=123456789,
            recorded_at='2026-03-31 10:05:00'
        )

        if success:
            print("✅ Test write absensi BERHASIL!")
            print("   Cek Google Sheets tab 'Absensi' untuk data test")
            return True
        else:
            print("❌ Test write absensi GAGAL!")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_write_audit():
    """Test write audit log."""
    print("\n" + "=" * 60)
    print("📝 Test Write: Audit Log")
    print("=" * 60)

    client = get_google_sheets_client()

    if not client.is_enabled():
        print("⚠️  Skip - Google Sheets tidak aktif")
        return False

    try:
        success = client.add_audit_log(
            user='test_admin',
            action='TEST',
            description='Test audit log entry dari test_google_sheets.py',
            timestamp='2026-03-31 10:10:00'
        )

        if success:
            print("✅ Test write audit log BERHASIL!")
            print("   Cek Google Sheets tab 'Audit' untuk data test")
            return True
        else:
            print("❌ Test write audit log GAGAL!")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Main test function."""
    print("\n🚀 Google Sheets Integration Test\n")

    # Test 1: Connection
    if not test_connection():
        print("\n⛔ Test dihentikan. Perbaiki koneksi terlebih dahulu.")
        return

    # Test 2: Write Jadwal
    test_write_jadwal()

    # Test 3: Write Absensi
    test_write_absensi()

    # Test 4: Write Audit
    test_write_audit()

    print("\n" + "=" * 60)
    print("✅ Semua test selesai!")
    print("=" * 60)
    print("\n📋 Langkah selanjutnya:")
    print("  1. Buka Google Sheets dan verifikasi data test")
    print("  2. Hapus data test dari Google Sheets (jika ada)")
    print("  3. Set GOOGLE_SHEET_SYNC_ENABLED = True di config.py")
    print("  4. Restart bot untuk enable auto-sync")
    print("\n")


if __name__ == '__main__':
    main()
