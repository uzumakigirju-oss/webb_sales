import json
import logging
import asyncio
from datetime import datetime
from aiogram import Router, F, types
from config import ALLOWED_USERS
from database import db_get_user_fair, db_shift_is_open
from sales_manager import write_sales_batch

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.web_app_data)
async def web_app_data_handler(message: types.Message) -> None:
    if not message.from_user or not message.web_app_data or message.from_user.id not in ALLOWED_USERS:
        return

    fair_name = await asyncio.to_thread(db_get_user_fair, message.from_user.id)
    if not fair_name or not await asyncio.to_thread(db_shift_is_open, fair_name):
        await message.answer("⚠️ Смена закрыта! Сначала откройте её.")
        return

    try:
        data = json.loads(message.web_app_data.data)
        cart = data.get("cart", [])
        payment_type = data.get("payment_type", "Наличные")

        cashier_id = message.from_user.id
        date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        total_sum = 0
        rows_to_write = []
        receipt_lines = []

        for item in cart:
            name = str(item["name"])
            price = int(item["price"])
            owner_id = int(item.get("owner_id", 0))
            qty = int(item.get("qty", 1))

            item_total = price * qty
            total_sum += item_total

            receipt_lines.append(f"  • {name}: {qty} шт. x {price} л. = {item_total} л.")

            for _ in range(qty):
                rows_to_write.append([date_now, name, price, owner_id, cashier_id, payment_type])

        # Асинхронно записываем чеки под блокировкой
        await write_sales_batch(fair_name, rows_to_write)

        logger.info(f"Действие: Продажа на {fair_name}. Пользователь: {message.from_user.first_name} ({cashier_id}). Сумма: {total_sum} л. Оплата: {payment_type}. Товары: {cart}")

        icon = "💳" if payment_type == "Карта" else "💵"
        receipt_text = "\n".join(receipt_lines)

        msg_text = (
            f"✅ <b>Новый чек пробит!</b>\n"
            f"Оплата: {icon} {payment_type}\n\n"
            f"<tg-spoiler>🧾 <b>Состав заказа:</b>\n"
            f"{receipt_text}</tg-spoiler>\n\n"
            f"💰 <b>Итого: {total_sum} лей</b>"
        )

        await message.answer(msg_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Failed to process and save WebApp sale: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка записи чека: {e}")
