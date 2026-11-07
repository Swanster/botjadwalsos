from config import DB_NAME
from core.database import create_tables


def migrate_user_groups():
    print(f"Migrating database: {DB_NAME}")
    try:
        create_tables()
        print("Migration successful!")
    except Exception as exc:
        print(f"Migration failed: {exc}")
        return False
    return True


if __name__ == "__main__":
    migrate_user_groups()
