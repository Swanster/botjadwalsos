import sqlite3
import os
from datetime import datetime
import calendar
import pytz
import contextlib

makassar_tz = pytz.timezone("Asia/Makassar")

from config import DB_NAME

def get_all_months_status():
    """Mengambil semua bulan yang pernah dibuka/ditutup dari status_bulanan."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT tahun, bulan, status FROM status_bulanan ORDER BY tahun DESC, bulan DESC")
        return [dict(row) for row in cur.fetchall()]

def row_to_dict(row):
    """Convert sqlite3.Row to dictionary."""
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}

@contextlib.contextmanager
def connect_db():
    conn = None
    try:
        os.makedirs(os.path.dirname(DB_NAME), exist_ok=True)
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        yield conn
    finally:
        if conn:
            conn.close()

def create_tables():
    """Membuat semua tabel yang diperlukan, termasuk 'user_groups'."""
    with connect_db() as conn:
        cur = conn.cursor()
        # ... (tabel status_bulanan, jadwal, absensi, konfigurasi, tukar_requests tetap sama) ...
        cur.execute('''
        CREATE TABLE IF NOT EXISTS status_bulanan (
            id INTEGER PRIMARY KEY, tahun INTEGER NOT NULL, bulan INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('DIBUKA', 'DITUTUP')), UNIQUE(tahun, bulan)
        )''')
        cur.execute('''
        CREATE TABLE IF NOT EXISTS jadwal (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            username TEXT NOT NULL, telegram_username TEXT, tanggal TEXT NOT NULL,
            UNIQUE(user_id, tanggal)
        )''')
        cur.execute('''
        CREATE TABLE IF NOT EXISTS absensi (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            tanggal_absen TEXT NOT NULL, UNIQUE(user_id, tanggal_absen)
        )''')
        cur.execute('''
        CREATE TABLE IF NOT EXISTS konfigurasi (
            kunci TEXT PRIMARY KEY, nilai TEXT NOT NULL
        )''')
        cur.execute('''
        CREATE TABLE IF NOT EXISTS tukar_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_a_id INTEGER NOT NULL, user_a_username TEXT NOT NULL,
            user_b_id INTEGER NOT NULL, tanggal_a TEXT NOT NULL, tanggal_b TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('PENDING', 'APPROVED', 'REJECTED')),
            waktu_request TEXT NOT NULL
        )''')
        
        # --- TABEL BARU ---
        cur.execute('''
        CREATE TABLE IF NOT EXISTS user_groups (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            telegram_username TEXT,
            group_name TEXT NOT NULL CHECK(group_name IN ('INFRA', 'CE', 'APPS', 'MONITORING'))
        )''')
        
        # --- TABEL SETTINGS (untuk kuota dinamis) ---
        cur.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            description TEXT
        )''')
        
        # --- TABEL ADMIN USERS (untuk login web dashboard) ---
        cur.execute('''
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )''')
        
        # --- TABEL DAILY LIMITS (untuk batasan per hari) ---
        cur.execute('''
        CREATE TABLE IF NOT EXISTS daily_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tanggal TEXT NOT NULL UNIQUE,
            max_assignments INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )''')
        
        # --- TABEL AUDIT LOGS (untuk mencatat aktivitas admin) ---
        cur.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            description TEXT,
            timestamp TEXT NOT NULL
        )''')
        
        conn.commit()
    print("Semua tabel (termasuk user_groups, settings, admin_users) berhasil diperiksa/dibuat.")

def set_user_group(user_id, username, telegram_username, group_name):
    """Menetapkan atau memperbarui grup (INFRA/CE) untuk seorang pengguna."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO user_groups (user_id, username, telegram_username, group_name) VALUES (?, ?, ?, ?)",
            (user_id, username, telegram_username, group_name.upper())
        )
        conn.commit()

def delete_user_from_group(user_id):
    """Menghapus pengguna dari tabel user_groups."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM user_groups WHERE user_id = ?", (user_id,))
        conn.commit()
        return cur.rowcount > 0

def get_user_group(user_id):
    """Mengambil grup dari seorang pengguna berdasarkan ID."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT group_name FROM user_groups WHERE user_id = ?", (user_id,))
        result = cur.fetchone()
        return result['group_name'] if result else None

def get_jadwal_by_group(tahun, bulan, group_name):
    """Mengambil semua jadwal untuk grup tertentu dalam sebulan.
    Username diambil dari user_groups sebagai sumber tunggal."""
    start_date = f"{tahun}-{bulan:02d}-01"
    end_date = f"{tahun}-{bulan:02d}-{calendar.monthrange(tahun, bulan)[1]}"
    with connect_db() as conn:
        cur = conn.cursor()
        query = """
            SELECT j.id, j.user_id, j.tanggal, 
                   ug.username, ug.telegram_username
            FROM jadwal j
            JOIN user_groups ug ON j.user_id = ug.user_id
            WHERE j.tanggal BETWEEN ? AND ? AND ug.group_name = ?
        """
        cur.execute(query, (start_date, end_date, group_name.upper()))
        return cur.fetchall()

def get_all_users_in_group(group_name):
    """Mengambil semua data pengguna dalam grup tertentu."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, username, telegram_username, group_name FROM user_groups WHERE group_name = ?", (group_name.upper(),))
        return cur.fetchall()

def populate_default_config():
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM konfigurasi")
        if cur.fetchone()[0] == 0:
            default_configs = [('kuota_per_hari', '2'), ('kuota_weekend', '1')]
            cur.executemany("INSERT INTO konfigurasi (kunci, nilai) VALUES (?, ?)", default_configs)
            conn.commit()
            print("🔧 Konfigurasi default berhasil dimasukkan.")

def format_tanggal_indonesia(tanggal_obj):
    nama_bulan = {1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'}
    return f"{tanggal_obj.day} {nama_bulan[tanggal_obj.month]} {tanggal_obj.year}"

def get_konfigurasi():
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT kunci, nilai FROM konfigurasi")
        return {row['kunci']: row['nilai'] for row in cur.fetchall()}

def update_user_jadwal_for_month(user_id, first_name, telegram_username, list_of_tanggal, tahun, bulan):
    start_of_month = f"{tahun}-{bulan:02d}-01"; end_of_month = f"{tahun}-{bulan:02d}-{calendar.monthrange(tahun, bulan)[1]}"
    with connect_db() as conn:
        try:
            cur = conn.cursor()
            cur.execute("BEGIN TRANSACTION;")
            cur.execute("DELETE FROM jadwal WHERE user_id = ? AND tanggal BETWEEN ? AND ?", (user_id, start_of_month, end_of_month))
            if list_of_tanggal:
                data_to_insert = [(user_id, first_name, telegram_username, tgl) for tgl in list_of_tanggal]
                cur.executemany("INSERT INTO jadwal (user_id, username, telegram_username, tanggal) VALUES (?, ?, ?, ?)", data_to_insert)
            conn.commit()
        except Exception as e:
            conn.rollback(); print(f"ERROR saat update_user_jadwal_for_month: {e}")

def get_bulan_dibuka():
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM status_bulanan WHERE status = 'DIBUKA'")
        return cur.fetchone()

def buka_bulan_baru(tahun, bulan):
    try:
        with connect_db() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO status_bulanan (tahun, bulan, status) VALUES (?, ?, 'DIBUKA')", (tahun, bulan))
            conn.commit()
            return cur.lastrowid
    except sqlite3.IntegrityError:
        return None

def get_jadwal_for_month(tahun, bulan):
    """Mengambil jadwal bulanan dengan username dari user_groups."""
    start_date = f"{tahun}-{bulan:02d}-01"
    end_date = f"{tahun}-{bulan:02d}-{calendar.monthrange(tahun, bulan)[1]}"
    with connect_db() as conn:
        cur = conn.cursor()
        query = """
            SELECT j.id, j.user_id, j.tanggal,
                   COALESCE(ug.username, j.username) as username,
                   COALESCE(ug.telegram_username, j.telegram_username) as telegram_username,
                   ug.group_name
            FROM jadwal j
            LEFT JOIN user_groups ug ON j.user_id = ug.user_id
            WHERE j.tanggal BETWEEN ? AND ?
        """
        cur.execute(query, (start_date, end_date))
        return [row_to_dict(row) for row in cur.fetchall()]

def get_user_absensi_in_range(user_id, start_date, end_date):
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT tanggal_absen FROM absensi WHERE user_id = ? AND tanggal_absen BETWEEN ? AND ?", (user_id, start_date, end_date))
        return {row['tanggal_absen'] for row in cur.fetchall()}

def set_user_absensi(user_id, list_of_tanggal, tahun, bulan):
    start_of_month = f"{tahun}-{bulan:02d}-01"; end_of_month = f"{tahun}-{bulan:02d}-{calendar.monthrange(tahun, bulan)[1]}"
    with connect_db() as conn:
        try:
            cur = conn.cursor()
            cur.execute("BEGIN TRANSACTION;")
            # Selalu hapus data lama di bulan tersebut terlebih dahulu
            cur.execute("DELETE FROM absensi WHERE user_id = ? AND tanggal_absen BETWEEN ? AND ?", (user_id, start_of_month, end_of_month))
            # Jika ada tanggal baru, masukkan
            if list_of_tanggal:
                data_to_insert = [(user_id, tgl) for tgl in list_of_tanggal]
                cur.executemany("INSERT INTO absensi (user_id, tanggal_absen) VALUES (?, ?)", data_to_insert)
            conn.commit()
        except Exception as e:
            conn.rollback(); print(f"ERROR saat set_user_absensi: {e}")

def get_user_jadwal_for_month(user_id, tahun, bulan):
    start_date = f"{tahun}-{bulan:02d}-01"; end_date = f"{tahun}-{bulan:02d}-{calendar.monthrange(tahun, bulan)[1]}"
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT tanggal FROM jadwal WHERE user_id = ? AND tanggal BETWEEN ? AND ? ORDER BY tanggal ASC", (user_id, start_date, end_date))
        return cur.fetchall()

def get_jadwal_for_specific_date(tanggal_str):
    """Mengambil jadwal untuk tanggal tertentu dengan username dari user_groups."""
    with connect_db() as conn:
        cur = conn.cursor()
        query = """
            SELECT j.id, j.user_id, j.tanggal,
                   COALESCE(ug.username, j.username) as username,
                   COALESCE(ug.telegram_username, j.telegram_username) as telegram_username,
                   ug.group_name
            FROM jadwal j
            LEFT JOIN user_groups ug ON j.user_id = ug.user_id
            WHERE j.tanggal = ?
        """
        cur.execute(query, (tanggal_str,))
        return [row_to_dict(row) for row in cur.fetchall()]

def get_user_by_telegram_username(username):
    """Mengambil user berdasarkan telegram username dari user_groups."""
    clean_username = username.lstrip('@')
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, username, telegram_username FROM user_groups WHERE telegram_username = ? COLLATE NOCASE LIMIT 1",
            (clean_username,)
        )
        return row_to_dict(cur.fetchone())

def create_tukar_request(user_a_id, user_a_username, user_b_id, tanggal_a, tanggal_b):
    waktu = datetime.now(pytz.timezone("Asia/Makassar")).strftime('%Y-%m-%d %H:%M:%S')
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("""INSERT INTO tukar_requests (user_a_id, user_a_username, user_b_id, tanggal_a, tanggal_b, status, waktu_request) VALUES (?, ?, ?, ?, ?, 'PENDING', ?)""", (user_a_id, user_a_username, user_b_id, tanggal_a, tanggal_b, waktu))
        conn.commit()
        return cur.lastrowid

def get_tukar_request_by_id(request_id):
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tukar_requests WHERE id = ?", (request_id,))
        return row_to_dict(cur.fetchone())

def execute_swap(request_id):
    """Menukar jadwal antara dua user. Username diambil dari user_groups."""
    req = get_tukar_request_by_id(request_id)
    if not req or req['status'] != 'PENDING': return False
    try:
        with connect_db() as conn:
            cur = conn.cursor()
            cur.execute("BEGIN TRANSACTION;")
            # Ambil detail user dari user_groups (sumber tunggal)
            user_b_details = cur.execute("SELECT username, telegram_username FROM user_groups WHERE user_id = ?", (req['user_b_id'],)).fetchone()
            user_a_details = cur.execute("SELECT username, telegram_username FROM user_groups WHERE user_id = ?", (req['user_a_id'],)).fetchone()
            if not user_a_details or not user_b_details: raise sqlite3.OperationalError("User details not found in user_groups.")
            # Swap hanya user_id, username otomatis dari JOIN
            cur.execute("UPDATE jadwal SET user_id = ?, username = ?, telegram_username = ? WHERE tanggal = ? AND user_id = ?", (req['user_b_id'], user_b_details['username'], user_b_details['telegram_username'], req['tanggal_a'], req['user_a_id']))
            cur.execute("UPDATE jadwal SET user_id = ?, username = ?, telegram_username = ? WHERE tanggal = ? AND user_id = ?", (req['user_a_id'], user_a_details['username'], user_a_details['telegram_username'], req['tanggal_b'], req['user_b_id']))
            cur.execute("UPDATE tukar_requests SET status = 'APPROVED' WHERE id = ?", (request_id,))
            conn.commit()
            return True
    except Exception as e:
        print(f"ERROR saat execute_swap: {e}")
        return False

def update_tukar_request_status(request_id, status):
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE tukar_requests SET status = ? WHERE id = ?", (status, request_id))
        conn.commit()
    
# --- PERUBAHAN DI SINI: Memperbaiki fungsi yang error di scheduler ---
def get_all_absensi_in_range(start_date, end_date):
    """
    Mengambil semua data absensi (cuti) dari semua pengguna
    dalam rentang tanggal yang diberikan. Username dari user_groups.
    """
    query = """
        SELECT
            a.tanggal_absen AS tanggal,
            ug.username
        FROM absensi a
        LEFT JOIN user_groups ug ON a.user_id = ug.user_id
        WHERE a.tanggal_absen BETWEEN ? AND ?
        ORDER BY a.tanggal_absen;
    """
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (start_date, end_date))
        # Filter out results where username is None (user not in user_groups)
        return [dict(row) for row in cursor.fetchall() if row['username'] is not None]
        
def tutup_bulan_aktif(tahun, bulan):
    """Mengubah status bulan yang 'DIBUKA' menjadi 'DITUTUP'."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE status_bulanan SET status = 'DITUTUP' WHERE tahun = ? AND bulan = ? AND status = 'DIBUKA'",
            (tahun, bulan)
        )
        conn.commit()
        # Mengembalikan jumlah baris yang diubah. Jika 1, berarti berhasil.
        return cur.rowcount

# NOTE: get_user_group dan get_jadwal_by_group sudah didefinisikan di atas (line ~104 dan ~112)


def get_all_registered_users():
    """Mengambil semua pengguna yang terdaftar di tabel user_groups."""
    with connect_db() as conn:
        cur = conn.cursor()
        # Mengambil user_id dan telegram_username untuk mention
        cur.execute("SELECT user_id, telegram_username FROM user_groups")
        return cur.fetchall()

def get_users_with_schedule_in_range(start_date, end_date):
    """Mengambil daftar unik user_id yang memiliki jadwal dalam rentang tanggal."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT user_id FROM jadwal WHERE tanggal BETWEEN ? AND ?", (start_date, end_date))
        # Mengembalikan sebuah set untuk perbandingan yang efisien
        return {row['user_id'] for row in cur.fetchall()}
        
def delete_user_jadwal_on_dates(user_id, list_of_tanggal_to_delete):
    """Menghapus jadwal pengguna pada tanggal-tanggal yang ditentukan."""
    if not list_of_tanggal_to_delete:
        return 0
    with connect_db() as conn:
        cur = conn.cursor()
        # Membuat placeholder (?) sebanyak jumlah tanggal yang akan dihapus
        placeholders = ', '.join('?' for _ in list_of_tanggal_to_delete)
        query = f"DELETE FROM jadwal WHERE user_id = ? AND tanggal IN ({placeholders})"
        
        # Gabungkan user_id dengan daftar tanggal untuk parameter query
        params = [user_id] + list_of_tanggal_to_delete
        
        cur.execute(query, params)
        conn.commit()
        # Mengembalikan jumlah baris yang terhapus
        return cur.rowcount

# =============================================================================
# SETTINGS FUNCTIONS (untuk kuota dinamis)
# =============================================================================

def get_setting(key, default=None):
    """Mengambil nilai setting dari database."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        result = cur.fetchone()
        return result['value'] if result else default

def set_setting(key, value, description=None):
    """Menyimpan atau memperbarui setting."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO settings (key, value, description) VALUES (?, ?, ?)",
            (key, str(value), description)
        )
        conn.commit()

def get_all_settings():
    """Mengambil semua settings sebagai dictionary."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT key, value, description FROM settings")
        return {row['key']: {'value': row['value'], 'description': row['description']} for row in cur.fetchall()}

def init_default_settings():
    """Inisialisasi settings default jika belum ada."""
    defaults = [
        ('kuota_infra', '2', 'Jumlah orang INFRA per hari'),
        ('kuota_ce', '1', 'Jumlah orang CE per hari'),
        ('max_hari_infra', '10', 'Maksimal hari standby per bulan untuk INFRA'),
        ('max_hari_ce', '31', 'Maksimal hari standby per bulan untuk CE'),
        ('kuota_apps', '1', 'Jumlah orang APPS per hari'),
        ('max_hari_apps', '31', 'Maksimal hari standby per bulan untuk APPS'),
        ('kuota_monitoring', '1', 'Jumlah orang Monitoring per hari'),
        ('max_hari_monitoring', '31', 'Maksimal hari standby per bulan untuk Monitoring'),
    ]
    with connect_db() as conn:
        cur = conn.cursor()
        for key, value, desc in defaults:
            cur.execute("SELECT 1 FROM settings WHERE key = ?", (key,))
            if not cur.fetchone():
                cur.execute("INSERT INTO settings (key, value, description) VALUES (?, ?, ?)", (key, value, desc))
        conn.commit()
    print("🔧 Default settings berhasil diinisialisasi.")

# =============================================================================
# ADMIN USER FUNCTIONS (untuk web dashboard login)
# =============================================================================

def add_admin_user(username, password):
    """Menambahkan admin user baru dengan password ter-hash."""
    import bcrypt
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    created_at = datetime.now(pytz.timezone("Asia/Makassar")).strftime('%Y-%m-%d %H:%M:%S')
    try:
        with connect_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO admin_users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, created_at)
            )
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False

def verify_admin(username, password):
    """Verifikasi kredensial admin. Return admin data jika valid, None jika tidak."""
    import bcrypt
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM admin_users WHERE username = ?", (username,))
        admin = cur.fetchone()
        if admin and bcrypt.checkpw(password.encode('utf-8'), admin['password_hash'].encode('utf-8')):
            return row_to_dict(admin)
        return None

def get_admin_by_username(username):
    """Mengambil data admin berdasarkan username."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, username, created_at FROM admin_users WHERE username = ?", (username,))
        result = cur.fetchone()
        return row_to_dict(result) if result else None

def update_admin_password(username, new_password):
    """Memperbarui password admin."""
    import bcrypt
    password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE admin_users SET password_hash = ? WHERE username = ?", (password_hash, username))
        conn.commit()
        return cur.rowcount > 0

def get_all_admin_users():
    """Mengambil semua admin users (tanpa password)."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, username, created_at FROM admin_users")
        return [row_to_dict(row) for row in cur.fetchall()]

def delete_admin_user(admin_id):
    """Menghapus admin user berdasarkan ID."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM admin_users WHERE id = ?", (admin_id,))
        conn.commit()
        return cur.rowcount > 0

def init_default_admin():
    """Inisialisasi admin default jika belum ada admin."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM admin_users")
        if cur.fetchone()[0] == 0:
            add_admin_user('admin', 'admin123')
            print("🔐 Default admin (admin/admin123) berhasil dibuat.")

# =============================================================================
# JADWAL MANUAL FUNCTIONS (untuk input jadwal via web)
# =============================================================================

def add_jadwal_manual(user_id, username, telegram_username, tanggal):
    """Menambahkan jadwal secara manual oleh admin."""
    try:
        with connect_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO jadwal (user_id, username, telegram_username, tanggal) VALUES (?, ?, ?, ?)",
                (user_id, username, telegram_username, tanggal)
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"Error add_jadwal_manual: {e}")
        return False

def delete_jadwal_by_id(jadwal_id):
    """Menghapus jadwal berdasarkan ID."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM jadwal WHERE id = ?", (jadwal_id,))
        conn.commit()
        return cur.rowcount > 0

# =============================================================================
# DAILY LIMITS FUNCTIONS
# =============================================================================

def set_daily_limit(tanggal, max_assignments):
    """Menetapkan batasan jumlah assignment untuk tanggal tertentu."""
    waktu = datetime.now(pytz.timezone("Asia/Makassar")).strftime('%Y-%m-%d %H:%M:%S')
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO daily_limits (tanggal, max_assignments, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (tanggal, max_assignments, waktu, waktu)
        )
        conn.commit()
        return cur.rowcount > 0

def get_daily_limit(tanggal, default_limit=1):
    """Mengambil batasan untuk tanggal tertentu. Jika tidak ada, kembalikan default."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT max_assignments FROM daily_limits WHERE tanggal = ?", (tanggal,))
        result = cur.fetchone()
        return result['max_assignments'] if result else default_limit

def get_all_daily_limits():
    """Mengambil semua batasan harian."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT tanggal, max_assignments, created_at, updated_at FROM daily_limits ORDER BY tanggal")
        return [dict(row) for row in cur.fetchall()]

def delete_daily_limit(tanggal):
    """Menghapus batasan untuk tanggal tertentu."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM daily_limits WHERE tanggal = ?", (tanggal,))
        conn.commit()
        return cur.rowcount > 0

def get_assignment_count_for_date(tanggal):
    """Menghitung jumlah assignment yang sudah ada untuk tanggal tertentu."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as count FROM jadwal WHERE tanggal = ?", (tanggal,))
        result = cur.fetchone()
        return result['count'] if result else 0

def is_date_full(tanggal, default_limit=1):
    """Mengecek apakah tanggal sudah penuh berdasarkan batasan."""
    limit = get_daily_limit(tanggal, default_limit)
    current_count = get_assignment_count_for_date(tanggal)
    return current_count >= limit

def add_audit_log(username, action, description):
    """Menambahkan catatan aktivitas ke tabel audit_logs."""
    timestamp = datetime.now(makassar_tz).strftime('%Y-%m-%d %H:%M:%S')
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute('''
        INSERT INTO audit_logs (username, action, description, timestamp)
        VALUES (?, ?, ?, ?)
        ''', (username, action, description, timestamp))
        conn.commit()

def get_audit_logs(limit=100):
    """Mengambil daftar log aktivitas terbaru."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute('SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?', (limit,))
        return cur.fetchall()