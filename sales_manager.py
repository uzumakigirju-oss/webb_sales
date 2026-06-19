import os
import csv
import asyncio
import logging
import secrets
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from config import PRODUCTS_FILE, ALLOWED_USERS
from database import (
    db_write_sales, db_get_sales_stats, db_get_sales_by_cashier,
    db_get_checks, db_get_check_items, db_archive_fair_sales
)

_fair_locks: Dict[str, asyncio.Lock] = {}

def get_fair_lock(fair_name: str) -> asyncio.Lock:
    name = fair_name.lower()
    if name not in _fair_locks:
        _fair_locks[name] = asyncio.Lock()
    return _fair_locks[name]

_products_cache = {
    "data": None,
    "mtime": 0.0,
    "size": 0
}

def invalidate_products_cache() -> None:
    _products_cache["data"] = None
    _products_cache["mtime"] = 0.0
    _products_cache["size"] = 0

def read_products_sync() -> List[Dict[str, Any]]:
    if not os.path.exists(PRODUCTS_FILE):
        return []

    try:
        stat = os.stat(PRODUCTS_FILE)
        current_mtime = stat.st_mtime
        current_size = stat.st_size
    except OSError:
        current_mtime = 0.0
        current_size = 0

    if _products_cache["data"] is not None and _products_cache["mtime"] == current_mtime and _products_cache.get("size", 0) == current_size:
        return _products_cache["data"]

    products = []
    try:
        with open(PRODUCTS_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 3:
                    continue
                try:
                    name = str(row[0].strip())
                    price = int(float(row[1].strip()))
                    owner_id = int(float(row[2].strip()))
                    if name and price > 0 and owner_id > 0:
                        products.append({"name": name, "price": price, "owner_id": owner_id})
                except (ValueError, AttributeError):
                    pass
    except Exception:
        if _products_cache["data"] is not None:
            return _products_cache["data"]
        return []

    _products_cache["data"] = products
    _products_cache["mtime"] = current_mtime
    _products_cache["size"] = current_size
    return products


async def read_products() -> List[Dict[str, Any]]:
    return await asyncio.to_thread(read_products_sync)


def generate_check_id() -> str:
    now = datetime.now()
    rand = secrets.token_hex(3)
    return f"CHK-{now.strftime('%Y%m%d-%H%M%S')}-{rand}"


def init_shift_sync(fair_name: str) -> None:
    pass


def get_current_stats_sync(fair_name: str) -> Tuple[Optional[Dict[int, Dict[str, Any]]], int]:
    rows = db_get_sales_stats(fair_name)
    if not rows:
        return None, 0

    summary_by_user: Dict[int, Dict[str, Any]] = {}
    grand_total = 0

    for row in rows:
        owner_id = row["owner_id"]
        item = row["item_name"]
        price = row["price"]
        payment_type = row["payment_type"]

        if owner_id not in summary_by_user:
            summary_by_user[owner_id] = {'items': {}, 'total': 0, 'card': 0}

        summary_by_user[owner_id]['items'][item] = summary_by_user[owner_id]['items'].get(item, 0) + 1
        summary_by_user[owner_id]['total'] += price

        if payment_type == "Карта":
            summary_by_user[owner_id]['card'] += price

        grand_total += price

    return summary_by_user, grand_total


def generate_report_sync(fair_name: str) -> Tuple[Optional[Dict[int, Dict[str, Any]]], Optional[int], Optional[str]]:
    summary_by_user, grand_total = get_current_stats_sync(fair_name)

    if not summary_by_user:
        return None, None, None

    now = datetime.now()
    folder = os.path.join("archives", str(now.year), f"{now.month:02d}")
    os.makedirs(folder, exist_ok=True)
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    saved_path = os.path.join(folder, f"sales_{fair_name.lower()}_{timestamp}.csv")

    try:
        with open(saved_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Дата', 'Товар', 'Цена', 'ID_Владельца', 'ID_Кассира', 'Тип_оплаты', 'ID_Чека'])
            for r in db_get_checks(fair_name):
                check_id = r["check_id"]
                items = db_get_check_items(fair_name, check_id)
                date_str = r["date"]
                payment_type = r["payment_type"]
                cashier_id = r["cashier_id"]
                for item in items:
                    writer.writerow([date_str, item["item_name"], item["price"], item["owner_id"], cashier_id, payment_type, check_id])
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to write archive CSV: {e}")
        saved_path = None

    db_archive_fair_sales(fair_name)

    return summary_by_user, grand_total, saved_path


def read_my_sales_sync(fair_name: str, cashier_id: int) -> Optional[Dict[str, Any]]:
    rows = db_get_sales_by_cashier(fair_name, cashier_id)
    if not rows:
        return None

    result: Dict[str, Any] = {'my_items': {'items': {}, 'total': 0, 'card': 0}, 'by_owner': {}}

    for row in rows:
        item = row["item_name"]
        price = row["price"]
        owner_id = row["owner_id"]
        payment_type = row["payment_type"]

        if owner_id == cashier_id:
            result['my_items']['items'][item] = result['my_items']['items'].get(item, 0) + 1
            result['my_items']['total'] += price
            if payment_type == "Карта":
                result['my_items']['card'] += price
        else:
            if owner_id not in result['by_owner']:
                result['by_owner'][owner_id] = {'items': {}, 'total': 0, 'card': 0}
            result['by_owner'][owner_id]['items'][item] = result['by_owner'][owner_id]['items'].get(item, 0) + 1
            result['by_owner'][owner_id]['total'] += price
            if payment_type == "Карта":
                result['by_owner'][owner_id]['card'] += price

    return result


def get_checks_sync(fair_name: str) -> List[Dict[str, Any]]:
    rows = db_get_checks(fair_name)
    if not rows:
        return []

    checks = []
    for r in rows:
        cashier_id = r["cashier_id"]
        items = db_get_check_items(fair_name, r["check_id"])
        formatted_items = []
        for item in items:
            formatted_items.append({
                "name": item["item_name"],
                "price": item["price"],
                "owner_id": item["owner_id"],
                "owner_name": ALLOWED_USERS.get(item["owner_id"], f"ID {item['owner_id']}"),
            })
        checks.append({
            "check_id": r["check_id"],
            "date": r["date"],
            "cashier_id": cashier_id,
            "cashier_name": ALLOWED_USERS.get(cashier_id, f"ID {cashier_id}"),
            "payment_type": r["payment_type"],
            "items": formatted_items,
            "total": r["total"],
        })

    return checks


def get_check_items_sync(fair_name: str, check_id: str) -> Optional[Dict[str, Any]]:
    checks = get_checks_sync(fair_name)
    for c in checks:
        if c["check_id"] == check_id:
            return c
    return None


async def write_sales_batch(fair_name: str, rows: List[List[Any]], check_id: str = "") -> None:
    async with get_fair_lock(fair_name):
        db_write_sales(fair_name, rows, check_id)


async def get_current_stats(fair_name: str) -> Tuple[Optional[Dict[int, Dict[str, Any]]], int]:
    async with get_fair_lock(fair_name):
        return await asyncio.to_thread(get_current_stats_sync, fair_name)


async def generate_report(fair_name: str) -> Tuple[Optional[Dict[int, Dict[str, Any]]], Optional[int], Optional[str]]:
    async with get_fair_lock(fair_name):
        return await asyncio.to_thread(generate_report_sync, fair_name)


async def read_my_sales(fair_name: str, cashier_id: int) -> Optional[Dict[str, Any]]:
    async with get_fair_lock(fair_name):
        return await asyncio.to_thread(read_my_sales_sync, fair_name, cashier_id)


def build_personal_stats_text_sync(fair_name: str, user_id: int) -> Optional[str]:
    user_name = ALLOWED_USERS.get(user_id, f"ID {user_id}")
    data = read_my_sales_sync(fair_name, user_id)
    if not data:
        return None

    my_items = data['my_items']
    by_owner = data['by_owner']
    if not my_items['items'] and not by_owner:
        return None

    text = f"📈 <b>Личная статистика {user_name} ({fair_name}):</b>\n\n"
    if my_items['items']:
        text += "🏷 <b>Мои товары:</b>\n"
        for item, count in my_items['items'].items():
            text += f"  • {item}: {count} шт.\n"
        text += f"  💰 Итого: <b>{my_items['total']} лей</b>\n"
        if my_items['card'] > 0:
            text += f"  💳 Из них терминал: {my_items['card']} лей\n"
        text += "\n"

    for owner_id, odata in by_owner.items():
        owner_name = ALLOWED_USERS.get(owner_id, f"ID {owner_id}")
        text += f"👤 <b>Товары {owner_name}:</b>\n"
        for item, count in odata['items'].items():
            text += f"  • {item}: {count} шт.\n"
        text += f"  💰 Итого: <b>{odata['total']} лей</b>\n"
        if odata['card'] > 0:
            text += f"  💳 Из них терминал: {odata['card']} лей\n"
        text += "\n"

    grand = my_items['total'] + sum(d['total'] for d in by_owner.values())
    text += f"💸 <b>Всего пробито: {grand} лей</b>"
    return text


async def build_personal_stats_text(fair_name: str, user_id: int) -> Optional[str]:
    async with get_fair_lock(fair_name):
        return await asyncio.to_thread(build_personal_stats_text_sync, fair_name, user_id)


async def get_checks(fair_name: str) -> List[Dict[str, Any]]:
    async with get_fair_lock(fair_name):
        return await asyncio.to_thread(get_checks_sync, fair_name)


async def get_check_items(fair_name: str, check_id: str) -> Optional[Dict[str, Any]]:
    async with get_fair_lock(fair_name):
        return await asyncio.to_thread(get_check_items_sync, fair_name, check_id)
