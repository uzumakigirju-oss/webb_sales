import os
import csv
import asyncio
import secrets
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from config import PRODUCTS_FILE, ALLOWED_USERS

# ──────────────────────────────────────────
# 🔒 БЛОКИРОВКИ И ОЧЕРЕДИ
# ──────────────────────────────────────────
_fair_locks: Dict[str, asyncio.Lock] = {}

def get_fair_lock(fair_name: str) -> asyncio.Lock:
    name = fair_name.lower()
    if name not in _fair_locks:
        _fair_locks[name] = asyncio.Lock()
    return _fair_locks[name]

# ──────────────────────────────────────────
# 📂 КЭШИРОВАНИЕ ТОВАРОВ
# ──────────────────────────────────────────
_products_cache = {
    "data": None,
    "mtime": 0.0,
    "size": 0
}

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
                    price = int(float(row[1].strip()))  # Handle both int and float with spaces
                    owner_id = int(float(row[2].strip()))  # Handle both int and float with spaces
                    if name and price > 0 and owner_id > 0:  # Validation
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

# ──────────────────────────────────────────
# 📝 CSV ОПЕРАЦИИ (СИНХРОННЫЕ)
# ──────────────────────────────────────────
def get_file_path(fair_name: str) -> str:
    return f"sales_{fair_name.lower()}.csv"


def generate_check_id() -> str:
    now = datetime.now()
    rand = secrets.token_hex(3)
    return f"CHK-{now.strftime('%Y%m%d-%H%M%S')}-{rand}"


def init_shift_sync(fair_name: str) -> None:
    file_path = get_file_path(fair_name)
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Дата', 'Товар', 'Цена', 'ID_Владельца', 'ID_Кассира', 'Тип_оплаты', 'ID_Чека'])


def write_sales_batch_sync(fair_name: str, rows: List[List[Any]], check_id: str = "") -> None:
    file_path = get_file_path(fair_name)
    with open(file_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        for row in rows:
            writer.writerow(list(row) + [check_id])


def get_current_stats_sync(fair_name: str) -> Tuple[Optional[Dict[int, Dict[str, Any]]], int]:
    file_path = get_file_path(fair_name)
    if not os.path.exists(file_path):
        return None, 0

    summary_by_user: Dict[int, Dict[str, Any]] = {}
    grand_total = 0

    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)

        for row in reader:
            if not row or 'Дата' in row[0]:
                continue
            if len(row) < 4:
                continue
            try:
                item = str(row[1])
                price = int(row[2])
                owner_id = int(row[3])
                payment_type = str(row[5]) if len(row) > 5 else "Наличные"
            except ValueError:
                continue

            if owner_id not in summary_by_user:
                summary_by_user[owner_id] = {'items': {}, 'total': 0, 'card': 0}

            summary_by_user[owner_id]['items'][item] = summary_by_user[owner_id]['items'].get(item, 0) + 1
            summary_by_user[owner_id]['total'] += price

            if payment_type == "Карта":
                summary_by_user[owner_id]['card'] += price

            grand_total += price

    return summary_by_user, grand_total


def generate_report_sync(fair_name: str) -> Tuple[Optional[Dict[int, Dict[str, Any]]], Optional[int], Optional[str]]:
    file_path = get_file_path(fair_name)
    summary_by_user, grand_total = get_current_stats_sync(fair_name)

    if not summary_by_user:
        return None, None, None

    now = datetime.now()
    folder = os.path.join("archives", str(now.year), f"{now.month:02d}")
    os.makedirs(folder, exist_ok=True)
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    saved_path = os.path.join(folder, f"sales_{fair_name.lower()}_{timestamp}.csv")
    os.rename(file_path, saved_path)

    return summary_by_user, grand_total, saved_path


def read_my_sales_sync(fair_name: str, cashier_id: int) -> Optional[Dict[str, Any]]:
    file_path = get_file_path(fair_name)
    if not os.path.exists(file_path):
        return None

    result: Dict[str, Any] = {'my_items': {'items': {}, 'total': 0, 'card': 0}, 'by_owner': {}}

    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or 'Дата' in row[0]:
                continue
            if len(row) < 5:
                continue
            try:
                item = str(row[1])
                price = int(row[2])
                owner_id = int(row[3])
                row_cashier = int(row[4])
                payment_type = str(row[5]) if len(row) > 5 else "Наличные"
            except ValueError:
                continue

            if row_cashier != cashier_id:
                continue

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
    file_path = get_file_path(fair_name)
    if not os.path.exists(file_path):
        return []

    checks: Dict[str, Dict] = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or 'Дата' in row[0]:
                continue
            if len(row) < 5:
                continue
            try:
                date_str = str(row[0])
                item = str(row[1])
                price = int(row[2])
                owner_id = int(row[3])
                cashier_id = int(row[4])
                payment_type = str(row[5]) if len(row) > 5 else "Наличные"
                check_id = str(row[6]) if len(row) > 6 and row[6] else f"ROW-{date_str}-{item}-{cashier_id}"
            except (ValueError, IndexError):
                continue

            if check_id not in checks:
                cashier_name = ALLOWED_USERS.get(cashier_id, f"ID {cashier_id}")
                checks[check_id] = {
                    "check_id": check_id,
                    "date": date_str,
                    "cashier_id": cashier_id,
                    "cashier_name": cashier_name,
                    "payment_type": payment_type,
                    "items": [],
                    "total": 0,
                }
            checks[check_id]["items"].append({
                "name": item,
                "price": price,
                "owner_id": owner_id,
                "owner_name": ALLOWED_USERS.get(owner_id, f"ID {owner_id}"),
            })
            checks[check_id]["total"] += price

    result = list(checks.values())
    result.sort(key=lambda c: c["date"], reverse=True)
    return result


def get_check_items_sync(fair_name: str, check_id: str) -> Optional[Dict[str, Any]]:
    checks = get_checks_sync(fair_name)
    for c in checks:
        if c["check_id"] == check_id:
            return c
    return None


# ──────────────────────────────────────────
# 🚀 АСИНХРОННЫЕ ОБЕРТКИ С БЛОКИРОВКАМИ
# ──────────────────────────────────────────
async def init_shift(fair_name: str) -> None:
    async with get_fair_lock(fair_name):
        await asyncio.to_thread(init_shift_sync, fair_name)


async def write_sales_batch(fair_name: str, rows: List[List[Any]], check_id: str = "") -> None:
    async with get_fair_lock(fair_name):
        await asyncio.to_thread(write_sales_batch_sync, fair_name, rows, check_id)


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
