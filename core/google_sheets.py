# core/google_sheets.py
"""
Google Sheets Integration Module
Handle sync data dari database ke Google Sheets secara real-time.
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Any

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GOOGLE_SHEETS_AVAILABLE = True
except ImportError:
    GOOGLE_SHEETS_AVAILABLE = False
    print("⚠️  gspread atau google-auth tidak terinstall. Google Sheets sync tidak aktif.")

from config import (
    GOOGLE_CREDENTIALS_FILE,
    GOOGLE_SHEET_ID,
    GOOGLE_SHEET_SYNC_ENABLED
)


class GoogleSheetsClient:
    """Client untuk integrasi Google Sheets."""

    def __init__(self):
        self.client = None
        self.spreadsheet = None
        self.jadwal_sheet = None
        self.absensi_sheet = None
        self.audit_sheet = None
        self.enabled = GOOGLE_SHEET_SYNC_ENABLED and GOOGLE_SHEETS_AVAILABLE
        self._initialize()

    def _initialize(self):
        """Inisialisasi koneksi ke Google Sheets."""
        if not self.enabled:
            print("📄 Google Sheets sync dinonaktifkan.")
            return

        try:
            # Validasi file credentials
            if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
                print(f"⚠️  File credentials tidak ditemukan: {GOOGLE_CREDENTIALS_FILE}")
                self.enabled = False
                return

            # Setup credentials
            credentials = Credentials.from_service_account_file(
                GOOGLE_CREDENTIALS_FILE,
                scopes=[
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive'
                ]
            )

            # Initialize client
            self.client = gspread.authorize(credentials)
            self.spreadsheet = self.client.open_by_key(GOOGLE_SHEET_ID)

            # Get atau create sheets
            self._ensure_sheets_exist()

            print(f"✅ Google Sheets connected: {self.spreadsheet.title}")

        except FileNotFoundError:
            print(f"❌ File credentials tidak ditemukan: {GOOGLE_CREDENTIALS_FILE}")
            self.enabled = False
        except gspread.exceptions.APIError as e:
            print(f"❌ Google Sheets API Error: {e}")
            self.enabled = False
        except Exception as e:
            print(f"❌ Error initializing Google Sheets: {e}")
            self.enabled = False

    def _ensure_sheets_exist(self):
        """Memastikan semua sheet tabs ada."""
        try:
            worksheets = self.spreadsheet.worksheets()
            sheet_names = [w.title for w in worksheets]

            # Cek dan buat sheet yang belum ada
            for sheet_name in ['Jadwal', 'Absensi', 'Audit']:
                if sheet_name not in sheet_names:
                    self.spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=10)
                    print(f"📝 Created sheet: {sheet_name}")

            # Get sheet references
            self.jadwal_sheet = self.spreadsheet.worksheet('Jadwal')
            self.absensi_sheet = self.spreadsheet.worksheet('Absensi')
            self.audit_sheet = self.spreadsheet.worksheet('Audit')

            # Setup headers jika sheet masih kosong
            self._setup_headers_if_needed()

        except Exception as e:
            print(f"⚠️  Error ensuring sheets exist: {e}")

    def _setup_headers_if_needed(self):
        """Setup header kolom jika sheet masih kosong."""
        try:
            # Jadwal headers - format sederhana
            jadwal_header = self.jadwal_sheet.row_values(1)
            if not jadwal_header:
                self.jadwal_sheet.append_row([
                    'Tanggal', 'Hari', 'Nama Anggota', 'Group'
                ])

            # Absensi headers
            absensi_header = self.absensi_sheet.row_values(1)
            if not absensi_header:
                self.absensi_sheet.append_row([
                    'Tanggal', 'Nama Anggota', 'Recorded At'
                ])

            # Audit headers
            audit_header = self.audit_sheet.row_values(1)
            if not audit_header:
                self.audit_sheet.append_row([
                    'Timestamp', 'User', 'Action', 'Description'
                ])

        except Exception as e:
            print(f"⚠️  Error setting up headers: {e}")

    def add_jadwal_entry(
        self,
        tanggal: str,
        hari: str,
        username: str,
        user_id: int,
        group: str,
        created_at: Optional[str] = None
    ) -> bool:
        """Tambahkan entry jadwal ke Google Sheets."""
        if not self.enabled:
            return False

        try:
            self.jadwal_sheet.append_row([
                tanggal, hari, username, group
            ])

            print(f"📝 [Google Sheets] Jadwal added: {username} @ {tanggal}")
            return True

        except Exception as e:
            print(f"❌ [Google Sheets] Error adding jadwal: {e}")
            return False

    def add_absensi_entry(
        self,
        tanggal: str,
        username: str,
        user_id: int,
        recorded_at: Optional[str] = None
    ) -> bool:
        """Tambahkan entry absensi ke Google Sheets."""
        if not self.enabled:
            return False

        try:
            if recorded_at is None:
                recorded_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            self.absensi_sheet.append_row([
                tanggal, username, str(user_id), recorded_at
            ])

            print(f"📝 [Google Sheets] Absensi added: {username} @ {tanggal}")
            return True

        except Exception as e:
            print(f"❌ [Google Sheets] Error adding absensi: {e}")
            return False

    def add_audit_log(
        self,
        user: str,
        action: str,
        description: str,
        timestamp: Optional[str] = None
    ) -> bool:
        """Tambahkan audit log ke Google Sheets."""
        if not self.enabled:
            return False

        try:
            if timestamp is None:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            self.audit_sheet.append_row([
                timestamp, user, action, description
            ])

            return True

        except Exception as e:
            print(f"❌ [Google Sheets] Error adding audit log: {e}")
            return False

    def sync_all_jadwal(self, jadwal_data: List[Dict[str, Any]]) -> bool:
        """
        Sync semua data jadwal (untuk full refresh).
        jadwal_data: List of dict dengan keys: tanggal, hari, username, group
        """
        if not self.enabled:
            return False

        try:
            # Clear existing data (keep header)
            self.jadwal_sheet.clear()

            # Set header - format sederhana
            self.jadwal_sheet.append_row([
                'Tanggal', 'Hari', 'Nama Anggota', 'Group'
            ])

            # Add all data
            rows = []
            for entry in jadwal_data:
                rows.append([
                    entry.get('tanggal', ''),
                    entry.get('hari', ''),
                    entry.get('username', ''),
                    entry.get('group', '')
                ])

            if rows:
                self.jadwal_sheet.append_rows(rows)

            print(f"📝 [Google Sheets] Synced {len(rows)} jadwal entries")
            return True

        except Exception as e:
            print(f"❌ [Google Sheets] Error syncing jadwal: {e}")
            return False

    def sync_all_absensi(self, absensi_data: List[Dict[str, Any]]) -> bool:
        """
        Sync semua data absensi (untuk full refresh).
        absensi_data: List of dict dengan keys: tanggal, username, user_id, recorded_at
        """
        if not self.enabled:
            return False

        try:
            # Clear existing data (keep header)
            self.absensi_sheet.clear()

            # Set header
            self.absensi_sheet.append_row([
                'Tanggal', 'Username', 'User ID', 'Recorded At'
            ])

            # Add all data
            rows = []
            for entry in absensi_data:
                rows.append([
                    entry.get('tanggal', ''),
                    entry.get('username', ''),
                    str(entry.get('user_id', '')),
                    entry.get('recorded_at', '')
                ])

            if rows:
                self.absensi_sheet.append_rows(rows)

            print(f"📝 [Google Sheets] Synced {len(rows)} absensi entries")
            return True

        except Exception as e:
            print(f"❌ [Google Sheets] Error syncing absensi: {e}")
            return False

    def get_sheet_url(self) -> str:
        """Dapatkan URL Google Sheets."""
        if self.spreadsheet:
            return self.spreadsheet.url
        return ""

    def is_enabled(self) -> bool:
        """Cek apakah Google Sheets sync aktif."""
        return self.enabled


# Singleton instance
_google_sheets_client: Optional[GoogleSheetsClient] = None


def get_google_sheets_client() -> GoogleSheetsClient:
    """Dapatkan instance Google Sheets client (singleton)."""
    global _google_sheets_client
    if _google_sheets_client is None:
        _google_sheets_client = GoogleSheetsClient()
    return _google_sheets_client


def sync_jadwal_to_sheets(tanggal: str, hari: str, username: str, group: str) -> bool:
    """
    Helper function untuk sync jadwal ke Google Sheets.
    Dipanggil setiap ada input jadwal baru.
    """
    client = get_google_sheets_client()
    return client.add_jadwal_entry(
        tanggal=tanggal,
        hari=hari,
        username=username,
        user_id=0,  # Tidak digunakan lagi
        group=group
    )


def sync_absensi_to_sheets(tanggal: str, username: str, user_id: int) -> bool:
    """
    Helper function untuk sync absensi ke Google Sheets.
    Dipanggil setiap ada input absensi baru.
    """
    client = get_google_sheets_client()
    return client.add_absensi_entry(
        tanggal=tanggal,
        username=username,
        user_id=user_id
    )


def log_audit_to_sheets(user: str, action: str, description: str) -> bool:
    """
    Helper function untuk log audit ke Google Sheets.
    """
    client = get_google_sheets_client()
    return client.add_audit_log(
        user=user,
        action=action,
        description=description
    )
