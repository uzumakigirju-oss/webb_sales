import sqlite3
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

DB_PATH = "bot_state.db"

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db() -> None:
    try:
        with get_conn() as conn:
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sales
                (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    fair_name TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    owner_id INTEGER NOT NULL,
                    cashier_id INTEGER NOT NULL,
                    payment_type TEXT NOT NULL DEFAULT 'Наличные',
                    archived INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_fair ON sales(fair_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_check ON sales(check_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_fair_archived ON sales(fair_name, archived)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_cashier ON sales(fair_name, cashier_id, archived)")
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


def db_write_sales(fair_name: str, rows: List[List], check_id: str = "") -> None:
    try:
        with get_conn() as conn:
            conn.executemany(
                "INSERT INTO sales (check_id, date, fair_name, item_name, price, owner_id, cashier_id, payment_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(check_id, row[0], fair_name, row[1], row[2], row[3], row[4], row[5]) for row in rows]
            )
    except sqlite3.Error as e:
        logger.error(f"DB error in db_write_sales: {e}")
        raise


def db_get_sales_stats(fair_name: str) -> tuple:
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT owner_id, item_name, price, payment_type FROM sales WHERE fair_name = ? AND archived = 0",
                (fair_name,)
            ).fetchall()
        return rows
    except sqlite3.Error as e:
        logger.error(f"DB error in db_get_sales_stats: {e}")
        return []


def db_get_sales_by_cashier(fair_name: str, cashier_id: int) -> List[sqlite3.Row]:
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT item_name, price, owner_id, cashier_id, payment_type FROM sales WHERE fair_name = ? AND archived = 0 AND cashier_id = ?",
                (fair_name, cashier_id)
            ).fetchall()
        return rows
    except sqlite3.Error as e:
        logger.error(f"DB error in db_get_sales_by_cashier: {e}")
        return []


def db_get_checks(fair_name: str) -> List[sqlite3.Row]:
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT check_id, date, cashier_id, payment_type, SUM(price) as total FROM sales WHERE fair_name = ? AND archived = 0 GROUP BY check_id ORDER BY date DESC",
                (fair_name,)
            ).fetchall()
        return rows
    except sqlite3.Error as e:
        logger.error(f"DB error in db_get_checks: {e}")
        return []


def db_get_check_items(fair_name: str, check_id: str) -> List[sqlite3.Row]:
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT item_name, price, owner_id FROM sales WHERE fair_name = ? AND check_id = ?",
                (fair_name, check_id)
            ).fetchall()
        return rows
    except sqlite3.Error as e:
        logger.error(f"DB error in db_get_check_items: {e}")
        return []


def db_archive_fair_sales(fair_name: str) -> None:
    try:
        with get_conn() as conn:
            conn.execute("UPDATE sales SET archived = 1 WHERE fair_name = ? AND archived = 0", (fair_name,))
    except sqlite3.Error as e:
        logger.error(f"DB error in db_archive_fair_sales: {e}")
        raise


def db_delete_check(fair_name: str, check_id: str) -> None:
    try:
        with get_conn() as conn:
            conn.execute("DELETE FROM sales WHERE fair_name = ? AND check_id = ?", (fair_name, check_id))
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"DB error in db_delete_check: {e}")
        raise


def db_migrate_fix_swapped_columns() -> None:
    try:
        with get_conn() as conn:
            cur = conn.execute("SELECT id, date, fair_name FROM sales WHERE date IN ('Yardsale', 'Ecolocal')")
            rows = cur.fetchall()
            if not rows:
                logger.info("Migration: no rows with swapped columns found")
                return
            for r in rows:
                conn.execute("UPDATE sales SET date = ?, fair_name = ? WHERE id = ?",
                             (r["fair_name"], r["date"], r["id"]))
            conn.commit()
            logger.info(f"Migration: fixed {len(rows)} rows with swapped date/fair_name columns")
    except sqlite3.Error as e:
        logger.error(f"DB migration error: {e}")
