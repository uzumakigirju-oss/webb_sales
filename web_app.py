import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets


import httpx
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

import aiofiles
from fastapi import FastAPI, Request, Response, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from itsdangerous import URLSafeTimedSerializer
from starlette.middleware.base import BaseHTTPMiddleware

from config import API_TOKEN, ALLOWED_USERS, PRODUCTS_FILE
from database import (
    init_db, db_get_user_fair, db_set_user_fair, db_remove_user_fair,
    db_get_shift_owner, db_open_shift, db_close_shift,
    db_get_users_on_fair, db_shift_is_open,
    db_create_login_code, db_get_login_user,
    db_migrate_fix_swapped_columns,
    db_delete_check
)
from sales_manager import (
    read_products, write_sales_batch, get_current_stats,
    generate_report, get_fair_lock, init_shift_sync,
    build_personal_stats_text_sync, generate_report_sync,
    read_my_sales_sync, get_current_stats_sync,
    generate_check_id, get_checks, get_check_items
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BOT_USERNAME = "sweetme_omnom_day_bot"
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
SECRET_KEY = os.getenv("WEB_SECRET", secrets.token_hex(32))
serializer = URLSafeTimedSerializer(SECRET_KEY, salt="web-session")
SHARED_FILES_DIR = Path("shared_files")
SHARED_FILES_META = Path("shared_files.json")
SHARED_FILES_DIR.mkdir(exist_ok=True)

os.makedirs("archives", exist_ok=True)

# ─── Auth helpers ────────────────────────────────────────────────

def verify_telegram_auth(data: dict) -> Optional[int]:
    received_hash = data.pop("hash", None)
    if not received_hash:
        return None
    auth_date = data.get("auth_date")
    if auth_date:
        dt = datetime.fromtimestamp(int(auth_date))
        if datetime.now() - dt > timedelta(hours=24):
            return None
    items = sorted(data.items())
    text = "\n".join(f"{k}={v}" for k, v in items)
    secret_key = hashlib.sha256(API_TOKEN.encode()).digest()
    computed = hmac.new(secret_key, text.encode(), hashlib.sha256).hexdigest()
    if computed != received_hash:
        return None
    user_id = int(data.get("id", 0))
    if user_id not in ALLOWED_USERS:
        return None
    return user_id


def create_session(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})


def get_session(request: Request) -> Optional[int]:
    token = request.cookies.get("session")
    if not token:
        return None
    try:
        data = serializer.loads(token, max_age=86400 * 7)
        uid = data.get("user_id")
        if uid in ALLOWED_USERS:
            return uid
    except Exception:
        pass
    return None


def get_user_name(user_id: int) -> str:
    return ALLOWED_USERS.get(user_id, f"ID {user_id}")


# ─── Auth code store (bot-based fallback) ────────────────────────

_auth_codes: Dict[int, str] = {}

def generate_auth_code(user_id: int) -> str:
    code = secrets.randbelow(900000) + 100000
    _auth_codes[user_id] = str(code)
    return str(code)


def verify_auth_code(user_id: int, code: str) -> bool:
    return _auth_codes.pop(user_id, None) == code


# ─── Lifecycle ───────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await asyncio.to_thread(db_migrate_fix_swapped_columns)
    logger.info("Web app started")
    yield
    logger.info("Web app stopped")


app = FastAPI(title="Omnom & SweetMe", lifespan=lifespan)

# ─── CORS middleware ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Auth middleware ─────────────────────────────────────────────

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        public_paths = {"/login", "/api/auth/telegram", "/api/auth/code", "/api/auth/me", "/api/auth/users", "/api/auth/login", "/api/auth/generate_login", "/api/auth/check_login", "/api/fair/status", "/static", "/favicon.ico"}
        path = request.url.path
        if any(path.startswith(p) for p in public_paths):
            return await call_next(request)
        user_id = get_session(request)
        if not user_id:
            if path.startswith("/api/"):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            return RedirectResponse(url="/login")
        request.state.user_id = user_id
        return await call_next(request)

app.add_middleware(AuthMiddleware)
app.mount("/static/images", StaticFiles(directory="images"), name="images")
app.mount("/static", StaticFiles(directory="static"), name="static")


# ─── Templates ──────────────────────────────────────────────────

from jinja2 import Environment, FileSystemLoader, select_autoescape

env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"]),
)


def render(template_name: str, **kwargs) -> str:
    t = env.get_template(template_name)
    return t.render(**kwargs)


# ─── API: Auth ──────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user_id = get_session(request)
    if user_id:
        return RedirectResponse(url="/")
    return render("login.html", bot_username=BOT_USERNAME, base_url=BASE_URL)


@app.get("/api/auth/telegram")
async def telegram_auth(request: Request, response: Response):
    data = dict(request.query_params)
    user_id = await asyncio.to_thread(verify_telegram_auth, data)
    if not user_id:
        return HTMLResponse("⛔ Доступ запрещён. Ваш Telegram ID не найден в списке разрешённых.", status_code=403)
    session_token = create_session(user_id)
    resp = RedirectResponse(url="/")
    resp.set_cookie(key="session", value=session_token, httponly=True, max_age=86400 * 7, samesite="lax")
    return resp


@app.get("/api/auth/code")
async def request_auth_code(user_id: int = Query(...)):
    if user_id not in ALLOWED_USERS:
        raise HTTPException(403, "Ваш ID не в списке разрешённых пользователей.")
    code = generate_auth_code(user_id)
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{API_TOKEN}/sendMessage",
                json={
                    "chat_id": user_id,
                    "text": f"🔑 <b>Код для входа в веб-кассу:</b> <code>{code}</code>\n\nВведите его на странице входа.",
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
    except Exception as e:
        logger.error(f"Failed to send auth code via Telegram: {e}")
        raise HTTPException(500, "Не удалось отправить код через Telegram. Убедитесь, что бот работает и вы написали ему /start.")
    logger.info(f"Auth code sent to user {user_id} ({get_user_name(user_id)})")
    return {"ok": True, "message": "Код отправлен в Telegram. Проверьте сообщение от бота."}


@app.post("/api/auth/code/verify")
async def verify_code(response: Response, user_id: int = Form(...), code: str = Form(...)):
    if not verify_auth_code(user_id, code):
        raise HTTPException(400, "Неверный код.")
    session_token = create_session(user_id)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(key="session", value=session_token, httponly=True, max_age=86400 * 7, samesite="lax")
    return resp


@app.get("/api/auth/me")
async def auth_me(request: Request):
    user_id = get_session(request)
    if not user_id:
        return JSONResponse({"authenticated": False}, status_code=401)
    return {
        "authenticated": True,
        "user_id": user_id,
        "name": get_user_name(user_id),
    }


@app.get("/api/auth/users")
async def auth_users():
    return {"users": ALLOWED_USERS}


@app.get("/api/auth/logout")
async def logout(response: Response):
    resp = RedirectResponse(url="/login")
    resp.delete_cookie("session")
    return resp


@app.post("/api/auth/login")
async def login_simple(response: Response, user_id: int = Form(...)):
    if user_id not in ALLOWED_USERS:
        raise HTTPException(403, "⛔ Доступ запрещён. Ваш ID не в списке разрешённых пользователей.")
    session_token = create_session(user_id)
    resp = JSONResponse({"ok": True, "name": get_user_name(user_id)})
    resp.set_cookie(key="session", value=session_token, httponly=True, max_age=86400 * 7, samesite="lax")
    logger.info(f"Login: {get_user_name(user_id)} ({user_id})")
    return resp

@app.get("/api/auth/generate_login")
async def generate_login():
    code = secrets.token_hex(8)
    await asyncio.to_thread(db_create_login_code, code)
    return {"ok": True, "code": code, "bot_link": f"https://t.me/{BOT_USERNAME}?start={code}"}

@app.get("/api/auth/check_login")
async def check_login(response: Response, code: str = Query(...)):
    user_id = await asyncio.to_thread(db_get_login_user, code)
    if user_id:
        session_token = create_session(user_id)
        resp = JSONResponse({"ok": True, "authenticated": True, "name": get_user_name(user_id)})
        resp.set_cookie(key="session", value=session_token, httponly=True, max_age=86400 * 7, samesite="lax")
        return resp
    return {"ok": True, "authenticated": False}


# ─── Helpers ─────────────────────────────────────────────────────

async def notify_all_users_task(text: str):
    async def send_one(uid):
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{API_TOKEN}/sendMessage",
                    json={
                        "chat_id": uid,
                        "text": text,
                        "parse_mode": "HTML",
                    },
                    timeout=5,
                )
        except Exception as e:
            logger.error(f"Failed to send notification to {uid}: {e}")
    await asyncio.gather(*(send_one(uid) for uid in ALLOWED_USERS))

def notify_all_users(text: str):
    asyncio.create_task(notify_all_users_task(text))

def _get_fair(user_id: int) -> Optional[str]:
    return db_get_user_fair(user_id)


async def _require_fair(user_id: int) -> str:
    fair = await asyncio.to_thread(_get_fair, user_id)
    if not fair:
        raise HTTPException(400, "Сначала выберите ярмарку.")
    return fair


async def _require_open_shift(user_id: int) -> str:
    fair = await _require_fair(user_id)
    if not await asyncio.to_thread(db_shift_is_open, fair):
        raise HTTPException(400, "Смена закрыта. Сначала откройте её.")
    return fair


# ─── API: Fair ──────────────────────────────────────────────────

@app.get("/api/fair/status")
async def fair_status(fair_name: str = Query(...)):
    shift_open = await asyncio.to_thread(db_shift_is_open, fair_name)
    shift_owner = await asyncio.to_thread(db_get_shift_owner, fair_name) if shift_open else None
    return {
        "fair_name": fair_name,
        "shift_open": shift_open,
        "shift_owner": shift_owner,
        "shift_owner_name": get_user_name(shift_owner) if shift_owner else None,
    }


@app.get("/api/fair")
async def get_fair(request: Request):
    user_id = request.state.user_id
    fair = await asyncio.to_thread(_get_fair, user_id)
    shift_open = await asyncio.to_thread(db_shift_is_open, fair) if fair else False
    shift_owner = await asyncio.to_thread(db_get_shift_owner, fair) if fair else None
    return {
        "fair": fair,
        "shift_open": shift_open,
        "shift_owner": shift_owner,
        "shift_owner_name": get_user_name(shift_owner) if shift_owner else None,
    }


@app.post("/api/fair")
async def set_fair(request: Request, fair_name: str = Form(...)):
    user_id = request.state.user_id
    valid_fairs = ["Yardsale", "Ecolocal"]
    if fair_name not in valid_fairs:
        raise HTTPException(400, "Некорректное название ярмарки.")
    current_fair = await asyncio.to_thread(_get_fair, user_id)
    if current_fair:
        is_open = await asyncio.to_thread(db_shift_is_open, current_fair)
        if is_open:
            my_sales = await asyncio.to_thread(read_my_sales_sync, current_fair, user_id)
            has_sales = my_sales and (bool(my_sales['my_items']['items']) or bool(my_sales['by_owner']))
            if has_sales:
                raise HTTPException(400, "У вас есть продажи в текущей смене. Сменить ярмарку можно после закрытия смены.")
        await asyncio.to_thread(db_remove_user_fair, user_id)
    await asyncio.to_thread(db_set_user_fair, user_id, fair_name)
    logger.info(f"Fair set: {fair_name} for user {user_id} ({get_user_name(user_id)})")
    notify_all_users(f"📍 <b>{get_user_name(user_id)}</b> присоединился к ярмарке <b>{fair_name}</b>.")
    return {"ok": True, "fair": fair_name}


# ─── API: Shift ─────────────────────────────────────────────────

@app.post("/api/shift/open")
async def open_shift(request: Request):
    user_id = request.state.user_id
    fair_name = await _require_fair(user_id)
    async with get_fair_lock(fair_name):
        if await asyncio.to_thread(db_shift_is_open, fair_name):
            raise HTTPException(400, "Смена уже открыта кем-то другим.")
        await asyncio.to_thread(db_open_shift, fair_name, user_id, datetime.now().isoformat())
        await asyncio.to_thread(init_shift_sync, fair_name)
        logger.info(f"Shift opened on {fair_name} by {get_user_name(user_id)} ({user_id})")
        notify_all_users(f"🟢 <b>{get_user_name(user_id)}</b> открыл смену на ярмарке <b>{fair_name}</b>!")
    return {"ok": True, "message": f"Смена на {fair_name} открыта!"}


@app.post("/api/shift/can-close")
async def can_close_shift(request: Request):
    user_id = request.state.user_id
    fair_name = await _require_fair(user_id)
    if not await asyncio.to_thread(db_shift_is_open, fair_name):
        return {"can_close": False, "reason": "Смена уже закрыта."}
    owner_id = await asyncio.to_thread(db_get_shift_owner, fair_name)
    if owner_id and owner_id != user_id:
        return {"can_close": False, "reason": "Закрыть смену может только тот, кто её открывал."}
    return {"can_close": True}


@app.post("/api/shift/close")
async def close_shift(request: Request):
    user_id = request.state.user_id
    fair_name = await _require_fair(user_id)
    if not await asyncio.to_thread(db_shift_is_open, fair_name):
        raise HTTPException(400, "Смена уже закрыта.")
    owner_id = await asyncio.to_thread(db_get_shift_owner, fair_name)
    if owner_id and owner_id != user_id:
        raise HTTPException(403, "Закрыть смену может только тот, кто её открывал.")
    async with get_fair_lock(fair_name):
        users_on_fair = await asyncio.to_thread(db_get_users_on_fair, fair_name)
        personal_stats = {}
        for uid in ALLOWED_USERS:
            text = await asyncio.to_thread(build_personal_stats_text_sync, fair_name, uid)
            if text:
                personal_stats[uid] = text
        summary_by_user, grand_total, saved_path = await asyncio.to_thread(generate_report_sync, fair_name)
        await asyncio.to_thread(db_close_shift, fair_name)
        logger.info(f"Shift closed on {fair_name} by {get_user_name(user_id)} ({user_id}). Total: {grand_total}")
    report_lines = []
    if summary_by_user:
        for owner_id, data in summary_by_user.items():
            oname = get_user_name(owner_id)
            report_lines.append(f"👤 <b>{oname}</b>")
            for item, count in data['items'].items():
                report_lines.append(f"  • {item}: {count} шт.")
            report_lines.append(f"  💰 Итого: <b>{data['total']} лей</b>")
            if data['card'] > 0:
                report_lines.append(f"  💳 Терминал: {data['card']} лей")
            report_lines.append("")
    else:
        report_lines.append("Продаж не было.\n")
    report_lines.append(f"💸 <b>ОБЩАЯ ВЫРУЧКА: {grand_total or 0} лей</b>")
    
    notify_all_users(f"🔴 <b>{get_user_name(user_id)}</b> закрыл смену на ярмарке <b>{fair_name}</b>.\n💸 Итоговая выручка: <b>{grand_total or 0} лей</b>.")
    
    return {
        "ok": True,
        "report": "\n".join(report_lines),
        "personal_stats": {str(uid): text for uid, text in personal_stats.items()},
        "saved_path": saved_path,
    }


# ─── API: Products ──────────────────────────────────────────────

@app.get("/api/products")
async def get_products():
    products = await read_products()
    return {"products": products}


# ─── API: Sales ─────────────────────────────────────────────────

@app.post("/api/sales")
async def record_sale(request: Request):
    user_id = request.state.user_id
    body = await request.json()
    cart = body.get("cart", [])
    payment_type = body.get("payment_type", "Наличные")
    fair_name = await _require_open_shift(user_id)
    date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    check_id = generate_check_id()
    total_sum = 0
    rows_to_write = []
    receipt_lines = []
    for item in cart:
        name = str(item["name"])
        price = int(item["price"])
        owner_id = int(item.get("owner_id", 0))
        qty = int(item.get("qty", 1))
        
        if qty <= 0:
            raise HTTPException(400, f"Ошибка в товаре '{name}': Количество должно быть > 0")
        if price < 0:
            raise HTTPException(400, f"Ошибка в товаре '{name}': Цена не может быть отрицательной")
            
        item_total = price * qty
        total_sum += item_total
        receipt_lines.append(f"  • {name}: {qty} шт. x {price} л. = {item_total} л.")
        for _ in range(qty):
            rows_to_write.append([date_now, name, price, owner_id, user_id, payment_type])
    await write_sales_batch(fair_name, rows_to_write, check_id)
    logger.info(f"Sale on {fair_name} by {get_user_name(user_id)} ({user_id}). Total: {total_sum}. Payment: {payment_type}")
    icon = "💳" if payment_type == "Карта" else "💵"
    
    notify_text = f"🧾 <b>Новый чек на ярмарке {fair_name}</b>\nКассир: {get_user_name(user_id)}\nСумма: {total_sum} лей {icon}\n\n" + "\n".join(receipt_lines)
    notify_all_users(notify_text)
    
    return {
        "ok": True,
        "total": total_sum,
        "payment_type": payment_type,
        "receipt": "\n".join(receipt_lines),
        "icon": icon,
    }


# ─── API: Stats ─────────────────────────────────────────────────

@app.get("/api/stats/me")
async def stats_me(request: Request):
    user_id = request.state.user_id
    fair_name = await _require_open_shift(user_id)
    text = await asyncio.to_thread(build_personal_stats_text_sync, fair_name, user_id)
    if not text:
        return {"stats": None, "message": "У вас пока нет продаж в текущей смене."}
    return {"stats": text}


@app.get("/api/stats/all")
async def stats_all(request: Request):
    user_id = request.state.user_id
    fair_name = await _require_open_shift(user_id)
    summary_by_user, grand_total = await get_current_stats(fair_name)
    if not summary_by_user:
        return {"stats": None, "message": "Продаж пока не было."}
    report = f"📊 <b>Общая статистика ({fair_name}):</b>\n\n"
    for owner_id, data in summary_by_user.items():
        oname = get_user_name(owner_id)
        report += f"👤 <b>{oname}</b>\n"
        for item, count in data['items'].items():
            report += f"  • {item}: {count} шт.\n"
        report += f"  💰 Итого: <b>{data['total']} лей</b>\n"
        if data['card'] > 0:
            report += f"  💳 Терминал: {data['card']} лей\n"
        report += "\n"
    report += f"💸 <b>ОБЩАЯ ВЫРУЧКА: {grand_total} лей</b>"
    return {"stats": report}


@app.get("/api/stats/checks")
async def stats_checks(request: Request):
    user_id = request.state.user_id
    fair_name = await _require_open_shift(user_id)
    checks = await get_checks(fair_name)
    if not checks:
        return {"checks": []}
    
    formatted_checks = []
    for c in checks:
        formatted_checks.append({
            "check_id": c["check_id"],
            "date": c["date"],
            "total": c["total"],
            "cashier_name": get_user_name(c["cashier_id"]),
            "payment_type": c["payment_type"],
        })
    return {"checks": formatted_checks}


@app.get("/api/stats/check/{check_id}")
async def stats_check_detail(request: Request, check_id: str):
    user_id = request.state.user_id
    fair_name = await _require_open_shift(user_id)
    
    checks = await get_checks(fair_name)
    check_meta = next((c for c in checks if c["check_id"] == check_id), None)
    if not check_meta:
        raise HTTPException(404, "Чек не найден.")
        
    items = await get_check_items(fair_name, check_id)
    
    formatted_items = []
    for i in items["items"]:
        formatted_items.append({
            "name": i["name"],
            "price": i["price"],
            "owner_name": get_user_name(i["owner_id"])
        })
        
    return {
        "check_id": check_id,
        "date": check_meta["date"],
        "total": check_meta["total"],
        "cashier_name": get_user_name(check_meta["cashier_id"]),
        "payment_type": check_meta["payment_type"],
        "items": formatted_items
    }


@app.delete("/api/stats/check/{check_id}")
async def delete_check(request: Request, check_id: str):
    user_id = request.state.user_id
    fair_name = await _require_open_shift(user_id)
    await asyncio.to_thread(db_delete_check, fair_name, check_id)
    logger.info(f"Check {check_id} deleted by {get_user_name(user_id)} ({user_id}) on {fair_name}")
    return {"ok": True}


# ─── API: Files ──────────────────────────────────────────────────

def _load_file_meta() -> List[Dict]:
    if not SHARED_FILES_META.exists():
        return []
    try:
        return json.loads(SHARED_FILES_META.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_file_meta(meta: List[Dict]):
    SHARED_FILES_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


@app.post("/api/files/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    user_id = request.state.user_id
    ext = Path(file.filename).suffix if file.filename else ".bin"
    file_id = str(uuid.uuid4())
    safe_name = f"{file_id}{ext}"
    dest = SHARED_FILES_DIR / safe_name
    content = await file.read()
    async with aiofiles.open(str(dest), "wb") as f:
        await f.write(content)
    meta = _load_file_meta()
    meta.append({
        "id": file_id,
        "original_name": file.filename or "unknown",
        "saved_name": safe_name,
        "uploader_id": user_id,
        "uploader_name": get_user_name(user_id),
        "timestamp": datetime.now().isoformat(),
        "size": len(content),
    })
    _save_file_meta(meta)
    logger.info(f"File uploaded by {get_user_name(user_id)}: {file.filename}")
    return {"ok": True, "file_id": file_id}


@app.get("/api/files")
async def list_files(request: Request):
    meta = _load_file_meta()
    return {"files": list(reversed(meta[-50:]))}


@app.get("/api/files/{file_id}")
async def download_file(file_id: str):
    meta = _load_file_meta()
    for m in meta:
        if m["id"] == file_id:
            dest = SHARED_FILES_DIR / m["saved_name"]
            if not dest.exists():
                raise HTTPException(404, "Файл не найден на диске.")
            return FileResponse(
                path=str(dest),
                filename=m["original_name"],
                media_type="application/octet-stream",
            )
    raise HTTPException(404, "Файл не найден.")


# ─── Main page ──────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user_id = get_session(request)
    if not user_id:
        return RedirectResponse(url="/login")
    return HTMLResponse(render("app.html", user_id=user_id, user_name=get_user_name(user_id)))


# ─── Run ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_app:app", host="0.0.0.0", port=8000, reload=True)
