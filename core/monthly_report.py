import calendar
from collections import defaultdict
from datetime import date, datetime

from core.database import (
    GROUP_NAMES,
    format_tanggal_indonesia,
    get_all_users_in_group,
    get_group_quota_status_for_date,
    get_jadwal_for_month,
    get_weekend_monthly_limit_key,
)
NAMA_BULAN = {
    1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni',
    7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
}
HARI_MAP_ID = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}


def _member_display_name(member):
    return member.get('username') or member.get('telegram_username') or str(member.get('user_id'))


def build_monthly_report(tahun, bulan):
    """Build monthly schedule report data for web and Telegram."""
    days_in_month = calendar.monthrange(tahun, bulan)[1]
    start_date = date(tahun, bulan, 1)
    end_date = date(tahun, bulan, days_in_month)
    jadwal_list = get_jadwal_for_month(tahun, bulan)

    members = []
    for group_name in GROUP_NAMES:
        for member in get_all_users_in_group(group_name):
            member_dict = dict(member)
            member_dict['display_name'] = _member_display_name(member_dict)
            members.append(member_dict)

    members_by_id = {member['user_id']: member for member in members}
    per_user = {
        member['user_id']: {
            'user_id': member['user_id'],
            'name': member['display_name'],
            'group_name': member.get('group_name', '-'),
            'count': 0,
            'saturday_count': 0,
            'sunday_count': 0,
        }
        for member in members
    }

    per_group = {
        group_name: {
            'group_name': group_name,
            'member_count': len([member for member in members if member.get('group_name') == group_name]),
            'total': 0,
            'average': 0,
        }
        for group_name in GROUP_NAMES
    }
    per_date = defaultdict(list)

    for jadwal in jadwal_list:
        user_id = jadwal['user_id']
        tanggal = jadwal['tanggal']
        group_name = jadwal.get('group_name') or members_by_id.get(user_id, {}).get('group_name', '-')
        name = jadwal.get('username') or jadwal.get('telegram_username') or members_by_id.get(user_id, {}).get('display_name') or str(user_id)

        if user_id not in per_user:
            per_user[user_id] = {
                'user_id': user_id,
                'name': name,
                'group_name': group_name,
                'count': 0,
                'saturday_count': 0,
                'sunday_count': 0,
            }

        per_user[user_id]['count'] += 1
        if group_name in per_group:
            per_group[group_name]['total'] += 1
        per_date[tanggal].append(jadwal)

        weekend_key = get_weekend_monthly_limit_key(tanggal)
        if weekend_key:
            if weekend_key[2] == 5:
                per_user[user_id]['saturday_count'] += 1
            elif weekend_key[2] == 6:
                per_user[user_id]['sunday_count'] += 1

    for group_stats in per_group.values():
        if group_stats['member_count']:
            group_stats['average'] = round(group_stats['total'] / group_stats['member_count'], 1)

    empty_dates = []
    full_dates = []
    under_quota = []
    over_quota = []
    for day in range(1, days_in_month + 1):
        tanggal = f'{tahun}-{bulan:02d}-{day:02d}'
        if not per_date.get(tanggal):
            empty_dates.append(tanggal)

        quota_status = get_group_quota_status_for_date(tanggal)
        all_groups_full = True
        for group_name in GROUP_NAMES:
            info = quota_status[group_name]
            if info['current'] < info['limit']:
                all_groups_full = False
                under_quota.append({
                    'tanggal': tanggal,
                    'group_name': group_name,
                    'current': info['current'],
                    'limit': info['limit'],
                })
            elif info['current'] > info['limit']:
                over_quota.append({
                    'tanggal': tanggal,
                    'group_name': group_name,
                    'current': info['current'],
                    'limit': info['limit'],
                })

        if all_groups_full:
            full_dates.append(tanggal)

    users_sorted = sorted(per_user.values(), key=lambda item: (-item['count'], item['group_name'], item['name'].lower()))
    zero_users = [user for user in users_sorted if user['count'] == 0]
    weekend_warnings = [
        user for user in users_sorted
        if user['saturday_count'] > 1 or user['sunday_count'] > 1
    ]

    return {
        'tahun': tahun,
        'bulan': bulan,
        'nama_bulan': NAMA_BULAN[bulan],
        'start_date': start_date,
        'end_date': end_date,
        'days_in_month': days_in_month,
        'total_assignments': len(jadwal_list),
        'empty_dates': empty_dates,
        'full_dates': full_dates,
        'under_quota_dates_count': len({item['tanggal'] for item in under_quota}),
        'under_quota': under_quota,
        'over_quota': over_quota,
        'per_group': [per_group[group_name] for group_name in GROUP_NAMES],
        'per_user': users_sorted,
        'zero_users': zero_users,
        'weekend_warnings': weekend_warnings,
    }


def format_monthly_report_for_telegram(report):
    """Format monthly report as a compact Telegram Markdown message."""
    title = f"📊 *Monthly Schedule Report - {report['nama_bulan']} {report['tahun']}*"
    period = f"_{format_tanggal_indonesia(report['start_date'])} - {format_tanggal_indonesia(report['end_date'])}_"
    lines = [
        title,
        period,
        "",
        f"Total Jadwal: *{report['total_assignments']}*",
        f"Hari Kosong: *{len(report['empty_dates'])}*",
        f"Hari Kurang Kuota: *{report['under_quota_dates_count']}*",
        f"Hari Penuh Semua Divisi: *{len(report['full_dates'])}*",
        "",
        "📌 *Per Divisi*",
    ]

    for group in report['per_group']:
        lines.append(
            f"- {group['group_name']}: *{group['total']}* jadwal "
            f"({group['member_count']} member, rata-rata {group['average']})"
        )

    lines.extend(["", "👤 *Per Orang*"])
    for user in report['per_user'][:20]:
        lines.append(f"- {user['name']} ({user['group_name']}): *{user['count']}*")

    if len(report['per_user']) > 20:
        lines.append(f"- ...dan {len(report['per_user']) - 20} member lainnya.")

    lines.extend(["", "⚠️ *Belum Ada Jadwal*"])
    if report['zero_users']:
        for user in report['zero_users'][:15]:
            lines.append(f"- {user['name']} ({user['group_name']})")
        if len(report['zero_users']) > 15:
            lines.append(f"- ...dan {len(report['zero_users']) - 15} member lainnya.")
    else:
        lines.append("- Tidak ada")

    lines.extend(["", "🗓️ *Tanggal Kurang Kuota*"])
    if report['under_quota']:
        for item in report['under_quota'][:20]:
            tanggal_obj = datetime.strptime(item['tanggal'], '%Y-%m-%d').date()
            hari = HARI_MAP_ID[tanggal_obj.weekday()]
            lines.append(
                f"- {hari}, {tanggal_obj.day}: {item['group_name']} "
                f"{item['current']}/{item['limit']}"
            )
        if len(report['under_quota']) > 20:
            lines.append(f"- ...dan {len(report['under_quota']) - 20} kekurangan lainnya.")
    else:
        lines.append("- Tidak ada")

    if report['over_quota'] or report['weekend_warnings']:
        lines.extend(["", "🚨 *Perlu Dicek*"])
        for item in report['over_quota'][:10]:
            tanggal_obj = datetime.strptime(item['tanggal'], '%Y-%m-%d').date()
            lines.append(
                f"- {tanggal_obj.day} {report['nama_bulan']}: {item['group_name']} "
                f"{item['current']}/{item['limit']} melebihi kuota"
            )
        for user in report['weekend_warnings'][:10]:
            lines.append(
                f"- {user['name']}: Sabtu {user['saturday_count']}x, "
                f"Minggu {user['sunday_count']}x"
            )

    return "\n".join(lines)
