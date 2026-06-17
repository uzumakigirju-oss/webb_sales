import asyncio
import logging
from datetime import datetime
from aiogram import Router, F, types
from aiogram.types import FSInputFile
from config import ALLOWED_USERS
from database import (
    db_get_user_fair, db_shift_is_open, db_open_shift, 
    db_get_shift_owner, db_get_users_on_fair, db_close_shift
)
from sales_manager import (
    get_fair_lock, init_shift_sync, build_personal_stats_text_sync, generate_report_sync
)
from keyboards import get_products_kb, get_start_kb, get_confirm_close_kb, get_choose_fair_kb

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "▶️ Начать смену")
async def open_shift(message: types.Message) -> None:
    if not message.from_user or message.from_user.id not in ALLOWED_USERS:
        return

    fair_name = await asyncio.to_thread(db_get_user_fair, message.from_user.id)
    if not fair_name:
        await message.answer("Сначала выберите ярмарку: /start")
        return

    async with get_fair_lock(fair_name):
        if await asyncio.to_thread(db_shift_is_open, fair_name):
            kb = await get_products_kb()
            await message.answer(f"⚠️ Смена на {fair_name} уже открыта кем-то другим! Вы присоединены.",
                                 reply_markup=kb)
            return

        await asyncio.to_thread(db_open_shift, fair_name, message.from_user.id, datetime.now().isoformat())
        await asyncio.to_thread(init_shift_sync, fair_name)

        logger.info(f"Действие: Открыта смена на {fair_name}. Пользователь: {message.from_user.first_name} ({message.from_user.id})")

    kb = await get_products_kb()
    await message.answer(f"✅ Вы открыли смену на <b>{fair_name}</b>! Успешных продаж.", reply_markup=kb,
                         parse_mode="HTML")

    for u_id in ALLOWED_USERS:
        if u_id != message.from_user.id:
            try:
                user_fair = await asyncio.to_thread(db_get_user_fair, u_id)
                if user_fair == fair_name:
                    await message.bot.send_message(u_id,
                                                   f"🟢 <b>Смена открыта!</b>\n{message.from_user.first_name} открыл(а) кассу на <b>{fair_name}</b>.",
                                                   reply_markup=kb,
                                                   parse_mode="HTML")
                else:
                    await message.bot.send_message(u_id,
                                                   f"🟢 <b>Смена открыта!</b>\n{message.from_user.first_name} открыл(а) кассу на <b>{fair_name}</b>.",
                                                   parse_mode="HTML")
            except Exception as e:
                logger.error(f"Failed to notify user {u_id} about open shift: {e}")


@router.message(F.text == "❌ Закрыть день")
async def request_close_day(message: types.Message) -> None:
    if not message.from_user or message.from_user.id not in ALLOWED_USERS:
        return

    fair_name = await asyncio.to_thread(db_get_user_fair, message.from_user.id)
    if not fair_name:
        return

    if not await asyncio.to_thread(db_shift_is_open, fair_name):
        await message.answer("⚠️ Смена уже закрыта!", reply_markup=get_start_kb())
        return

    owner_id = await asyncio.to_thread(db_get_shift_owner, fair_name)
    if owner_id and owner_id != message.from_user.id:
        await message.answer("⛔ <b>Отказано.</b>\nЗакрыть смену может только тот, кто её открывал!", parse_mode="HTML")
        return

    await message.answer(f"Вы уверены, что хотите закрыть ярмарку <b>{fair_name}</b>?",
                         reply_markup=get_confirm_close_kb(), parse_mode="HTML")


@router.callback_query(F.data == "cancel_close")
async def cancel_close_handler(callback: types.CallbackQuery) -> None:
    if not callback.from_user or callback.from_user.id not in ALLOWED_USERS:
        return

    if isinstance(callback.message, types.Message):
        await callback.message.edit_text("Действие отменено. Смена продолжается ✅")

    await callback.answer()


@router.callback_query(F.data == "confirm_close")
async def confirm_close_handler(callback: types.CallbackQuery) -> None:
    if not callback.from_user or callback.from_user.id not in ALLOWED_USERS or not callback.message:
        return

    fair_name = await asyncio.to_thread(db_get_user_fair, callback.from_user.id)

    if not fair_name or not await asyncio.to_thread(db_shift_is_open, fair_name):
        if isinstance(callback.message, types.Message):
            await callback.message.edit_text("⚠️ Ошибка: смена не найдена или уже закрыта.")
        await callback.answer()
        return

    if isinstance(callback.message, types.Message):
        await callback.message.delete()

    # Атомарно выполняем закрытие смены под блокировкой, чтобы исключить Race Conditions
    async with get_fair_lock(fair_name):
        users_on_fair = await asyncio.to_thread(db_get_users_on_fair, fair_name)
        personal_stats = {}
        for uid in ALLOWED_USERS:
            personal_stats[uid] = await asyncio.to_thread(build_personal_stats_text_sync, fair_name, uid)

        summary_by_user, grand_total, saved_path = await asyncio.to_thread(generate_report_sync, fair_name)
        await asyncio.to_thread(db_close_shift, fair_name)

        logger.info(f"Действие: Закрыта смена на {fair_name}. Пользователь: {callback.from_user.first_name} ({callback.from_user.id}). Итого: {grand_total}")

    report = f"📊 <b>Итоги за сегодня ({fair_name}):</b>\n\n"

    if summary_by_user:
        for owner_id, data in summary_by_user.items():
            owner_name = ALLOWED_USERS.get(owner_id, f"ID {owner_id}")
            report += f"👤 <b>{owner_name}</b>\n"
            for item, count in data['items'].items():
                report += f"  • {item}: {count} шт.\n"
            report += f"  💰 Итого: <b>{data['total']} лей</b>\n"
            if data['card'] > 0:
                report += f"  💳 Из них по терминалу: {data['card']} лей\n"
            report += "\n"
    else:
        report += "Продаж не было.\n\n"

    report += f"💸 <b>ОБЩАЯ ВЫРУЧКА: {grand_total or 0} лей</b>"

    caption = f"🔴 <b>СМЕНА ЗАКРЫТА ({fair_name})</b>\nЗакрыл: {callback.from_user.first_name}\n\n{report}"

    for user_id in ALLOWED_USERS:
        try:
            if saved_path:
                await callback.message.bot.send_document(chat_id=user_id, document=FSInputFile(saved_path), caption=caption,
                                                         parse_mode="HTML")
            else:
                await callback.message.bot.send_message(chat_id=user_id, text=caption, parse_mode="HTML")

            personal = personal_stats.get(user_id)
            if personal:
                await callback.message.bot.send_message(chat_id=user_id, text=personal, parse_mode="HTML")

            if user_id in users_on_fair:
                await callback.message.bot.send_message(user_id, "Смена завершена. Вы можете выбрать другую ярмарку:",
                                                        reply_markup=get_choose_fair_kb())
        except Exception as e:
            logger.error(f"Failed to send shift closure report to user {user_id}: {e}")

    await callback.answer("Смена успешно закрыта!")
