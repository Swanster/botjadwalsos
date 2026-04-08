# web/app.py - Flask Web Dashboard untuk Bot Jadwal SOS

import os
import sys
from datetime import datetime, date
from functools import wraps
import calendar

from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import (
    verify_admin, get_admin_by_username, update_admin_password, get_all_admin_users,
    add_admin_user, delete_admin_user,
    get_all_users_in_group, set_user_group, get_user_group, delete_user_from_group,
    get_jadwal_for_month, get_jadwal_for_specific_date, add_jadwal_manual, delete_jadwal_by_id,
    get_bulan_dibuka, format_tanggal_indonesia,
    create_tables, init_default_admin,
    set_daily_limit, get_all_daily_limits, delete_daily_limit, get_daily_limit,
    is_date_full, add_audit_log, get_audit_logs,
    get_all_settings, set_setting
)
from core.google_sheets import sync_jadwal_to_sheets, sync_absensi_to_sheets, get_google_sheets_client

# =============================================================================
# FLASK APP SETUP (Fixed - removed settings dependency, added daily limits validation)
# =============================================================================

def create_app():
    app = Flask(__name__)
    app.secret_key = os.urandom(24)
    
    # Initialize database tables and defaults
    create_tables()
    init_default_admin()
    
    # Flask-Login setup
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Silakan login untuk mengakses halaman ini.'
    
    class User(UserMixin):
        def __init__(self, username):
            self.id = username
            self.username = username
    
    @login_manager.user_loader
    def load_user(username):
        admin = get_admin_by_username(username)
        if admin:
            return User(admin['username'])
        return None

    # =============================================================================
    # ROUTES - AUTH
    # =============================================================================
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            username = request.form.get('username', '')
            password = request.form.get('password', '')

            admin = verify_admin(username, password)
            if admin:
                user = User(admin['username'])
                login_user(user)
                add_audit_log(username, 'LOGIN', 'Berhasil login ke dashboard web')
                flash('Login berhasil!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Username atau password salah.', 'error')

        # Get calendar data for current month (like schedules page)
        from datetime import date
        today = date.today()
        year = request.args.get('year', today.year, type=int)
        month = request.args.get('month', today.month, type=int)

        # Get schedules for the month
        jadwal_list = get_jadwal_for_month(year, month)

        # Build member lookup for group info
        members_infra = [dict(m) for m in get_all_users_in_group('INFRA')]
        members_ce = [dict(m) for m in get_all_users_in_group('CE')]
        members_apps = [dict(m) for m in get_all_users_in_group('APPS')]
        members_monitoring = [dict(m) for m in get_all_users_in_group('MONITORING')]
        all_members = members_infra + members_ce + members_apps + members_monitoring

        # Create user_id to group_name mapping
        user_group_map = {}
        for m in all_members:
            user_group_map[m['user_id']] = m.get('group_name', '-')

        # Organize by date and add group_name
        jadwal_per_tanggal = {}
        for j in jadwal_list:
            tanggal = j['tanggal']
            j_dict = dict(j)
            # Add group_name from lookup
            j_dict['group_name'] = user_group_map.get(j['user_id'], '-')
            if tanggal not in jadwal_per_tanggal:
                jadwal_per_tanggal[tanggal] = []
            jadwal_per_tanggal[tanggal].append(j_dict)

        # Calendar info
        import calendar as cal_module
        cal = cal_module.Calendar(firstweekday=cal_module.MONDAY)
        month_calendar = cal.monthdayscalendar(year, month)

        # Get daily limits for this month
        daily_limits_info = {}
        for week in month_calendar:
            for day in week:
                if day != 0:
                    date_str = f'{year}-{month:02d}-{day:02d}'
                    limit = get_daily_limit(date_str, 1)
                    current_count = len(jadwal_per_tanggal.get(date_str, []))
                    is_full = current_count >= limit
                    daily_limits_info[date_str] = {
                        'limit': limit,
                        'current': current_count,
                        'is_full': is_full
                    }

        NAMA_BULAN = {1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni',
                      7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'}

        return render_template('login.html',
            year=year,
            month=month,
            month_name=NAMA_BULAN[month],
            month_calendar=month_calendar,
            jadwal_per_tanggal=jadwal_per_tanggal,
            all_members=all_members,
            daily_limits=daily_limits_info
        )
    
    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('Anda telah logout.', 'info')
        return redirect(url_for('login'))

    # =============================================================================
    # ROUTES - DASHBOARD
    # =============================================================================
    
    @app.route('/')
    @login_required
    def index():
        return redirect(url_for('dashboard'))
    
    @app.route('/dashboard')
    @login_required
    def dashboard():
        import pytz
        makassar_tz = pytz.timezone("Asia/Makassar")
        today = datetime.now(makassar_tz).date()
        
        # Get today's schedule
        today_str = today.strftime('%Y-%m-%d')
        jadwal_hari_ini = get_jadwal_for_specific_date(today_str)
        
        # Get current month schedule
        jadwal_bulan_ini = get_jadwal_for_month(today.year, today.month)
        
        # Get all members
        members_infra = get_all_users_in_group('INFRA')
        members_ce = get_all_users_in_group('CE')
        members_apps = get_all_users_in_group('APPS')
        members_monitoring = get_all_users_in_group('MONITORING')
        
        # Get open month info
        bulan_dibuka = get_bulan_dibuka()
        
        return render_template('dashboard.html',
            today=today,
            today_str=format_tanggal_indonesia(today),
            jadwal_hari_ini=jadwal_hari_ini,
            jadwal_bulan_ini=jadwal_bulan_ini,
            members_infra=members_infra,
            members_ce=members_ce,
            members_apps=members_apps,
            members_monitoring=members_monitoring,
            bulan_dibuka=bulan_dibuka
        )

    # =============================================================================
    # ROUTES - MEMBERS
    # =============================================================================
    
    @app.route('/members')
    @login_required
    def members():
        members_infra = get_all_users_in_group('INFRA')
        members_ce = get_all_users_in_group('CE')
        members_apps = get_all_users_in_group('APPS')
        members_monitoring = get_all_users_in_group('MONITORING')
        return render_template('members.html', 
            members_infra=members_infra, 
            members_ce=members_ce,
            members_apps=members_apps,
            members_monitoring=members_monitoring
        )
    
    @app.route('/members/add', methods=['POST'])
    @login_required
    def add_member():
        user_id = request.form.get('user_id', '').strip()
        username = request.form.get('username', '').strip()
        telegram_username = request.form.get('telegram_username', '').strip()
        group_name = request.form.get('group_name', 'INFRA')
        
        if not user_id or not username:
            flash('User ID dan Username wajib diisi.', 'error')
            return redirect(url_for('members'))
        
        try:
            user_id = int(user_id)
            set_user_group(user_id, username, telegram_username, group_name)
            flash(f'Member {username} berhasil ditambahkan ke grup {group_name}.', 'success')
        except ValueError:
            flash('User ID harus berupa angka.', 'error')
        
        return redirect(url_for('members'))
    
    @app.route('/members/<int:user_id>/update', methods=['POST'])
    @login_required
    def update_member(user_id):
        username = request.form.get('username', '').strip()
        telegram_username = request.form.get('telegram_username', '').strip()
        group_name = request.form.get('group_name', 'INFRA')
        
        set_user_group(user_id, username, telegram_username, group_name)
        flash(f'Member {username} berhasil diperbarui.', 'success')
        return redirect(url_for('members'))
    
    @app.route('/members/<int:user_id>/delete', methods=['POST'])
    @login_required
    def delete_member(user_id):
        if delete_user_from_group(user_id):
            flash('Member berhasil dihapus.', 'success')
        else:
            flash('Gagal menghapus member.', 'error')
        return redirect(url_for('members'))

    # =============================================================================
    # ROUTES - SCHEDULES (MANUAL INPUT)
    # =============================================================================
    
    @app.route('/schedules')
    @login_required
    def schedules():
        today = date.today()
        year = request.args.get('year', today.year, type=int)
        month = request.args.get('month', today.month, type=int)

        # Get schedules for the month
        jadwal_list = get_jadwal_for_month(year, month)

        # Build member lookup for group info
        members_infra = [dict(m) for m in get_all_users_in_group('INFRA')]
        members_ce = [dict(m) for m in get_all_users_in_group('CE')]
        members_apps = [dict(m) for m in get_all_users_in_group('APPS')]
        members_monitoring = [dict(m) for m in get_all_users_in_group('MONITORING')]
        all_members = members_infra + members_ce + members_apps + members_monitoring
        
        # Create user_id to group_name mapping
        user_group_map = {}
        for m in all_members:
            user_group_map[m['user_id']] = m.get('group_name', '-')

        # Organize by date and add group_name
        jadwal_per_tanggal = {}
        for j in jadwal_list:
            tanggal = j['tanggal']
            j_dict = dict(j)
            # Add group_name from lookup
            j_dict['group_name'] = user_group_map.get(j['user_id'], '-')
            if tanggal not in jadwal_per_tanggal:
                jadwal_per_tanggal[tanggal] = []
            jadwal_per_tanggal[tanggal].append(j_dict)

        # Calendar info
        cal = calendar.Calendar(firstweekday=calendar.MONDAY)
        month_calendar = cal.monthdayscalendar(year, month)

        # Get daily limits for this month
        daily_limits_info = {}
        for week in month_calendar:
            for day in week:
                if day != 0:
                    date_str = f'{year}-{month:02d}-{day:02d}'
                    limit = get_daily_limit(date_str, 1)
                    current_count = len(jadwal_per_tanggal.get(date_str, []))
                    is_full = current_count >= limit
                    daily_limits_info[date_str] = {
                        'limit': limit,
                        'current': current_count,
                        'is_full': is_full
                    }

        NAMA_BULAN = {1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni',
                      7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'}

        return render_template('schedules.html',
            year=year,
            month=month,
            month_name=NAMA_BULAN[month],
            month_calendar=month_calendar,
            jadwal_per_tanggal=jadwal_per_tanggal,
            all_members=all_members,
            daily_limits=daily_limits_info
        )
    
    @app.route('/schedules/add', methods=['POST'])
    @login_required
    def add_schedule():
        user_id = request.form.get('user_id', '').strip()
        tanggal = request.form.get('tanggal', '').strip()
        
        if not user_id or not tanggal:
            flash('User dan tanggal wajib dipilih.', 'error')
            return redirect(url_for('schedules'))
        
        try:
            user_id = int(user_id)
            # Get user info
            user_group = get_user_group(user_id)
            if not user_group:
                flash('User tidak ditemukan.', 'error')
                return redirect(url_for('schedules'))
            
            # Get username from members - convert sqlite3.Row to dict
            members_infra = [dict(m) for m in get_all_users_in_group('INFRA')]
            members_ce = [dict(m) for m in get_all_users_in_group('CE')]
            members_apps = [dict(m) for m in get_all_users_in_group('APPS')]
            members_monitoring = [dict(m) for m in get_all_users_in_group('MONITORING')]
            members = members_infra + members_ce + members_apps + members_monitoring
            
            username = ''
            telegram_username = ''
            for m in members:
                if m['user_id'] == user_id:
                    username = m.get('username') or ''
                    telegram_username = m.get('telegram_username') or ''
                    break
            
            # Check daily limit before adding
            if is_date_full(tanggal, 1):
                max_limit = get_daily_limit(tanggal, 1)
                flash(f'❌ Tanggal {tanggal} sudah penuh ({max_limit} orang). Tidak bisa menambah jadwal.', 'error')
                return redirect(url_for('schedules'))
            
            if add_jadwal_manual(user_id, username, telegram_username, tanggal):
                add_audit_log(current_user.username, 'ADD_SCHEDULE', f'Menambah jadwal manual untuk {username} ({user_id}) pada tanggal {tanggal}')

                # Sync ke Google Sheets
                user_group = get_user_group(user_id)
                hari_map = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}
                from datetime import datetime
                hari = hari_map[datetime.strptime(tanggal, '%Y-%m-%d').weekday()]
                sync_jadwal_to_sheets(
                    tanggal=tanggal,
                    hari=hari,
                    username=telegram_username or username,
                    group=user_group or 'UNKNOWN'
                )

                flash(f'Jadwal untuk {username} pada {tanggal} berhasil ditambahkan.', 'success')
            else:
                flash('Gagal menambahkan jadwal.', 'error')
        except ValueError:
            flash('User ID tidak valid.', 'error')
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
        
        return redirect(url_for('schedules'))
    
    @app.route('/schedules/<int:jadwal_id>/delete', methods=['POST'])
    @login_required
    def delete_schedule(jadwal_id):
        if delete_jadwal_by_id(jadwal_id):
            add_audit_log(current_user.username, 'DELETE_SCHEDULE', f'Menghapus jadwal dengan ID {jadwal_id}')
            flash('Jadwal berhasil dihapus.', 'success')
        else:
            flash('Gagal menghapus jadwal.', 'error')
        return redirect(url_for('schedules'))

    # =============================================================================
    # ROUTES - PASSWORD RESET
    # =============================================================================
    
    @app.route('/password', methods=['GET', 'POST'])
    @login_required
    def change_password():
        if request.method == 'POST':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            if new_password != confirm_password:
                flash('Password baru tidak cocok.', 'error')
                return redirect(url_for('change_password'))
            
            if len(new_password) < 6:
                flash('Password minimal 6 karakter.', 'error')
                return redirect(url_for('change_password'))
            
            # Verify current password
            admin = verify_admin(current_user.username, current_password)
            if not admin:
                flash('Password saat ini salah.', 'error')
                return redirect(url_for('change_password'))
            
            # Update password
            if update_admin_password(current_user.username, new_password):
                flash('Password berhasil diperbarui!', 'success')
            else:
                flash('Gagal memperbarui password.', 'error')
            
            return redirect(url_for('change_password'))
        
        return render_template('password.html')
    
    @app.route('/admins')
    @login_required
    def admins():
        admin_list = get_all_admin_users()
        return render_template('admins.html', admins=admin_list)
    
    @app.route('/logs')
    @login_required
    def logs():
        recent_logs = get_audit_logs(limit=200)
        return render_template('logs.html', logs=recent_logs)
    
    @app.route('/admins/add', methods=['POST'])
    @login_required
    def add_admin():
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            flash('Username dan password wajib diisi.', 'error')
            return redirect(url_for('admins'))
        
        if len(password) < 6:
            flash('Password minimal 6 karakter.', 'error')
            return redirect(url_for('admins'))
        
        if add_admin_user(username, password):
            flash(f'Admin {username} berhasil ditambahkan.', 'success')
        else:
            flash(f'Username {username} sudah ada.', 'error')
        
        return redirect(url_for('admins'))
    
    @app.route('/admins/<int:admin_id>/delete', methods=['POST'])
    @login_required
    def delete_admin(admin_id):
        if delete_admin_user(admin_id):
            flash('Admin berhasil dihapus.', 'success')
        else:
            flash('Gagal menghapus admin.', 'error')
        return redirect(url_for('admins'))
    
    @app.route('/admins/<int:admin_id>/reset', methods=['POST'])
    @login_required
    def reset_admin_password(admin_id):
        new_password = request.form.get('new_password', '').strip()
        
        if len(new_password) < 6:
            flash('Password minimal 6 karakter.', 'error')
            return redirect(url_for('admins'))
        
        # Get admin username by id
        admins = get_all_admin_users()
        username = None
        for a in admins:
            if a['id'] == admin_id:
                username = a['username']
                break
        
        if username and update_admin_password(username, new_password):
            flash(f'Password untuk {username} berhasil direset.', 'success')
        else:
            flash('Gagal mereset password.', 'error')
        
        return redirect(url_for('admins'))

    # =============================================================================
    # ROUTES - SETTINGS
    # =============================================================================
    
    @app.route('/settings', methods=['GET', 'POST'])
    @login_required
    def settings():
        if request.method == 'POST':
            # Update all settings from form
            keys = [
                'kuota_infra', 'kuota_ce', 'kuota_apps', 'kuota_monitoring',
                'max_hari_infra', 'max_hari_ce', 'max_hari_apps', 'max_hari_monitoring'
            ]
            
            for key in keys:
                value = request.form.get(key)
                if value is not None:
                    set_setting(key, value)
            
            add_audit_log(current_user.username, 'UPDATE_SETTINGS', 'Memperbarui batasan kuota per grup')
            flash('Pengaturan kuota berhasil diperbarui.', 'success')
            return redirect(url_for('settings'))
            
        all_settings = get_all_settings()
        return render_template('settings.html', settings=all_settings)


    # =============================================================================
    # ROUTES - DAILY LIMITS
    # =============================================================================
    
    @app.route('/daily-limits', methods=['GET', 'POST'])
    @login_required
    def daily_limits():
        if request.method == 'POST':
            # Check if this is bulk monthly setting
            if request.form.get('bulk_set') == 'true':
                return handle_bulk_monthly_limits(request)
            
            # Regular single day setting
            tanggal = request.form.get('tanggal', '').strip()
            max_assignments = request.form.get('max_assignments', '').strip()
            
            if not tanggal or not max_assignments:
                flash('Tanggal dan batasan wajib diisi.', 'error')
                return redirect(url_for('daily_limits'))
            
            try:
                max_assignments = int(max_assignments)
                if max_assignments < 1:
                    flash('Batasan minimal 1 orang.', 'error')
                    return redirect(url_for('daily_limits'))
                
                if set_daily_limit(tanggal, max_assignments):
                    flash(f'Batasan untuk tanggal {tanggal} berhasil disimpan ({max_assignments} orang).', 'success')
                else:
                    flash('Gagal menyimpan batasan.', 'error')
            except ValueError:
                flash('Batasan harus berupa angka.', 'error')
            
            return redirect(url_for('daily_limits'))
        
        # Get all daily limits
        limits = get_all_daily_limits()
        from datetime import datetime
        current_year = datetime.now().year
        return render_template('daily_limits.html', limits=limits, current_year=current_year)
    
    @app.route('/daily-limits/<tanggal>/delete', methods=['POST'])
    @login_required
    def delete_daily_limit_route(tanggal):
        if delete_daily_limit(tanggal):
            flash(f'Batasan untuk tanggal {tanggal} berhasil dihapus.', 'success')
        else:
            flash('Gagal menghapus batasan.', 'error')
        return redirect(url_for('daily_limits'))
    
    def handle_bulk_monthly_limits(request):
        """Handle bulk setting of daily limits for an entire month."""
        from datetime import datetime
        import calendar
        
        bulan = request.form.get('bulan', '').strip()
        tahun = request.form.get('tahun', '').strip()
        max_assignments = request.form.get('max_assignments_bulan', '').strip()
        
        if not bulan or not tahun or not max_assignments:
            flash('Bulan, tahun, dan batasan wajib diisi untuk setting bulanan.', 'error')
            return redirect(url_for('daily_limits'))
        
        try:
            bulan = int(bulan)
            tahun = int(tahun)
            max_assignments = int(max_assignments)
            
            if max_assignments < 1:
                flash('Batasan minimal 1 orang.', 'error')
                return redirect(url_for('daily_limits'))
            
            # Generate all dates in the month
            days_in_month = calendar.monthrange(tahun, bulan)[1]
            success_count = 0
            
            for day in range(1, days_in_month + 1):
                tanggal = f"{tahun}-{bulan:02d}-{day:02d}"
                if set_daily_limit(tanggal, max_assignments):
                    success_count += 1
            
            flash(f'Berhasil mengatur batasan {max_assignments} orang/hari untuk {success_count} tanggal di bulan {bulan}/{tahun}.', 'success')
            
        except ValueError:
            flash('Format bulan, tahun, atau batasan tidak valid.', 'error')
        except Exception as e:
            flash(f'Terjadi error: {str(e)}', 'error')
        
        return redirect(url_for('daily_limits'))

    # =============================================================================
    # ROUTES - GOOGLE SHEETS SYNC
    # =============================================================================

    @app.route('/google-sheets')
    @login_required
    def google_sheets():
        """Halaman status Google Sheets integration."""
        client = get_google_sheets_client()
        is_enabled = client.is_enabled()
        sheet_url = client.get_sheet_url() if is_enabled else None
        
        return render_template('google_sheets.html', 
                             is_enabled=is_enabled, 
                             sheet_url=sheet_url)

    @app.route('/google-sheets/sync-all', methods=['POST'])
    @login_required
    def sync_all_to_sheets():
        """Full sync semua data jadwal dan absensi ke Google Sheets (hanya bulan berjalan)."""
        try:
            from core.database import get_all_absensi_in_range, get_jadwal_for_month

            client = get_google_sheets_client()

            if not client.is_enabled():
                flash('Google Sheets sync belum aktif. Periksa konfigurasi.', 'error')
                return redirect(url_for('google_sheets'))

            # Sync semua jadwal (hanya bulan yang sedang berjalan)
            from datetime import datetime, timedelta
            now = datetime.now()
            hari_map = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}

            all_jadwal = []
            # Hanya ambil data bulan ini
            jadwal_data = get_jadwal_for_month(now.year, now.month)
            for j in jadwal_data:
                date_obj = datetime.strptime(j['tanggal'], '%Y-%m-%d')
                all_jadwal.append({
                    'tanggal': j['tanggal'],
                    'hari': hari_map[date_obj.weekday()],
                    'username': j.get('telegram_username') or j.get('username'),
                    'group': j.get('group_name') or 'UNKNOWN'
                })

            client.sync_all_jadwal(all_jadwal)

            # Sync semua absensi (hanya bulan yang sedang berjalan)
            # Ambil dari awal bulan sampai akhir bulan
            start_date = now.replace(day=1).strftime('%Y-%m-%d')
            # Cari hari terakhir bulan ini
            if now.month == 12:
                end_date = f"{now.year}-12-31"
            else:
                next_month = now.replace(month=now.month + 1, day=1)
                end_date = (next_month - timedelta(days=1)).strftime('%Y-%m-%d')
            
            absensi_data = get_all_absensi_in_range(start_date, end_date)

            all_absensi = []
            for a in absensi_data:
                all_absensi.append({
                    'tanggal': a['tanggal'],
                    'username': a.get('username', 'Unknown'),
                    'user_id': 0,  # Tidak tersedia di data absensi
                    'recorded_at': ''
                })

            client.sync_all_absensi(all_absensi)

            add_audit_log(current_user.username, 'GOOGLE_SHEETS_SYNC', 'Full sync data ke Google Sheets berhasil')
            flash(f'✅ Full sync berhasil! {len(all_jadwal)} jadwal dan {len(all_absensi)} absensi disinkronkan.', 'success')

        except Exception as e:
            flash(f'❌ Error saat sync: {str(e)}', 'error')

        return redirect(url_for('google_sheets'))

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5050, debug=True)
