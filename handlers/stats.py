import logging
import asyncio
from aiogram import Router, types
from aiogram.filters import Command
from config import ALLOWED_USERS
from database import db_get_user_fair, db_shift_is_open
from sales_manager import build_personal_stats_text, get_current_stats

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("stats"))
async def stats_handler(message: types.Message) -> None:
    if not message.from_user or message.from_user.id not in ALLOWED_USERS:
        return

    fair_name = await asyncio.to_thread(db_get_user_fair, message.from_user.id)
    if not fair_name:
        await message.answer("Сначала выберите ярмарку: /start")
        return

    if not await asyncio.to_thread(db_shift_is_open, fair_name):
        await message.answer("⚠️ Смена закрыта.")
        return

    # Получаем личную статистику под блокировкой
    report = await build_personal_stats_text(fair_name, message.from_user.id)
    if not report:
        await message.answer(f"📈 У тебя пока нет продаж в текущей смене, {message.from_user.first_name}.")
        return

    await message.answer(report, parse_mode="HTML")


@router.message(Command("statsall"))
async def statsall_handler(message: types.Message) -> None:
    if not message.from_user or message.from_user.id not in ALLOWED_USERS:
        return

    fair_name = await asyncio.to_thread(db_get_user_fair, message.from_user.id)
    if not fair_name:
        await message.answer("Сначала выберите ярмарку: /start")
        return

    if not await asyncio.to_thread(db_shift_is_open, fair_name):
        await message.answer("⚠️ Смена закрыта.")
        return

    # Получаем общие продажи под блокировкой
    summary_by_user, grand_total = await get_current_stats(fair_name)

    if not summary_by_user:
        await message.answer(f"📊 <b>Общая статистика ({fair_name}):</b>\n\nПродаж пока не было.", parse_mode="HTML")
        return

    report = f"📊 <b>Общая статистика ({fair_name}):</b>\n\n"
    for owner_id, data in summary_by_user.items():
        owner_name = ALLOWED_USERS.get(owner_id, f"ID {owner_id}")
        report += f"👤 <b>{owner_name}</b>\n"
        for item, count in data['items'].items():
            report += f"  • {item}: {count} шт.\n"
        report += f"  💰 Итого: <b>{data['total']} лей</b>\n"
        if data['card'] > 0:
            report += f"  💳 Из них по терминалу: {data['card']} лей\n"
        report += "\n"

    report += f"💸 <b>ОБЩАЯ ВЫРУЧКА: {grand_total} лей</b>"
    await message.answer(report, parse_mode="HTML")
