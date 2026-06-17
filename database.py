import sqlite3
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

DB_PATH = "bot_state.db"

def init_db() -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                         CREATE TABLE IF NOT EXISTS active_fairs
                         (
                             user_id INTEGER PRIMARY KEY,
                             fair_name TEXT NOT NULL
                         )
                         """)
            conn.execute("""
                         CREATE TABLE IF NOT EXISTS shifts
                         (
                             fair_name TEXT PRIMARY KEY,
                             owner_id INTEGER NOT NULL,
                             opened_at TEXT NOT NULL
                         )
                         """)
            conn.execute("""
                         CREATE TABLE IF NOT EXISTS login_codes
                         (
                             code TEXT PRIMARY KEY,
                             user_id INTEGER,
                             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                         )
                         """)
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"DB error in init_db: {e}")


def db_get_user_fair(user_id: int) -> Optional[str]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute("SELECT fair_name FROM active_fairs WHERE user_id = ?", (user_id,)).fetchone()
        return str(row[0]) if row else None
    except sqlite3.Error as e:
        logger.error(f"DB error in db_get_user_fair: {e}")
        return None


def db_set_user_fair(user_id: int, fair_name: str) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT OR REPLACE INTO active_fairs (user_id, fair_name) VALUES (?, ?)", (user_id, fair_name))
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"DB error in db_set_user_fair: {e}")


def db_remove_user_fair(user_id: int) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM active_fairs WHERE user_id = ?", (user_id,))
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"DB error in db_remove_user_fair: {e}")


def db_get_shift_owner(fair_name: str) -> Optional[int]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute("SELECT owner_id FROM shifts WHERE fair_name = ?", (fair_name,)).fetchone()
        return int(row[0]) if row else None
    except sqlite3.Error as e:
        logger.error(f"DB error in db_get_shift_owner: {e}")
        return None


def db_open_shift(fair_name: str, owner_id: int, opened_at: str) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT OR REPLACE INTO shifts (fair_name, owner_id, opened_at) VALUES (?, ?, ?)",
                         (fair_name, owner_id, opened_at))
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"DB error in db_open_shift: {e}")


def db_close_shift(fair_name: str) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM shifts WHERE fair_name = ?", (fair_name,))
            conn.execute("DELETE FROM active_fairs WHERE fair_name = ?", (fair_name,))
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"DB error in db_close_shift: {e}")


def db_get_users_on_fair(fair_name: str) -> List[int]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT user_id FROM active_fairs WHERE fair_name = ?", (fair_name,)).fetchall()
        return [int(r[0]) for r in rows]
    except sqlite3.Error as e:
        logger.error(f"DB error in db_get_users_on_fair: {e}")
        return []


def db_shift_is_open(fair_name: str) -> bool:
    return db_get_shift_owner(fair_name) is not None


def db_create_login_code(code: str) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT OR REPLACE INTO login_codes (code, user_id) VALUES (?, NULL)", (code,))
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"DB error in db_create_login_code: {e}")

def db_set_login_user(code: str, user_id: int) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE login_codes SET user_id = ? WHERE code = ?", (user_id, code))
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"DB error in db_set_login_user: {e}")

def db_get_login_user(code: str) -> Optional[int]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute("SELECT user_id FROM login_codes WHERE code = ?", (code,)).fetchone()
        return int(row[0]) if row and row[0] is not None else None
    except sqlite3.Error as e:
        logger.error(f"DB error in db_get_login_user: {e}")
        return None
