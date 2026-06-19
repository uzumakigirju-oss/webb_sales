import asyncio
import logging
from datetime import datetime
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from config import ALLOWED_USERS, get_web_app_url
from database import db_get_user_fair, db_shift_is_open, db_remove_user_fair, db_set_user_fair, db_open_shift, db_set_login_user
from keyboards import get_choose_fair_kb, get_start_kb, get_products_kb, get_join_or_switch_kb
from sales_manager import read_my_sales_sync, get_fair_lock, init_shift_sync, invalidate_products_cache

logger = logging.getLogger(__name__)
router = Router()

def web_app_btn() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Открыть веб-кассу", web_app=WebAppInfo(url=get_web_app_url()))]
    ])

@router.message(Command("start"))
async def start_handler(message: types.Message) -> None:
    if not message.from_user or message.from_user.id not in ALLOWED_USERS:
        await message.answer("⛔ У вас нет доступа к кассе.")
        return

    parts = message.text.split()
    if len(parts) > 1:
        login_code = parts[1]
        await asyncio.to_thread(db_set_login_user, login_code, message.from_user.id)
        await message.answer("✅ Вы успешно авторизованы в кассе! Вкладка в браузере обновится автоматически.")
        return

    current_fair = await asyncio.to_thread(db_get_user_fair, message.from_user.id)

    if current_fair and await asyncio.to_thread(db_shift_is_open, current_fair):
        kb = await get_products_kb()
        await message.answer(
            f"⚠️ Вы закреплены за ярмаркой <b>{current_fair}</b>.\nСменить её можно после закрытия текущей смены.",
            reply_markup=kb, parse_mode="HTML")
        return

    await asyncio.to_thread(db_remove_user_fair, message.from_user.id)
    await message.answer(
        f"👋 Доброе утро!\n\n"
        f"Выберите ярмарку ниже или откройте веб-кассу по кнопке:",
        reply_markup=get_choose_fair_kb())
    await message.answer(
        "🌐 <b>Веб-касса</b> — полноценный интерфейс в браузере:",
        reply_markup=web_app_btn(), parse_mode="HTML")


@router.message(Command("link"))
async def share_webapp_link(message: types.Message) -> None:
    if not message.from_user or message.from_user.id not in ALLOWED_USERS:
        return
    url = get_web_app_url()
    sent = 0
    for uid in ALLOWED_USERS:
        try:
            await message.bot.send_message(
                uid,
                f"🌐 <b>Ссылка на веб-кассу:</b>\n\n{url}\n\n"
                f"Откройте в браузере на телефоне или компьютере.",
                parse_mode="HTML"
            )
            sent += 1
        except Exception as e:
            logger.error(f"Failed to send link to {uid}: {e}")
    await message.answer(f"✅ Ссылка отправлена {sent} пользователям.")


@router.message(Command("refresh"))
async def refresh_products(message: types.Message) -> None:
    if not message.from_user or message.from_user.id not in ALLOWED_USERS:
        return
    invalidate_products_cache()
    await message.answer("✅ Кэш товаров сброшен. Товары будут загружены заново при следующем обращении.")


@router.message(F.text.in_(["🎪 Yardsale", "🌿 Ecolocal", "🔙 Сменить ярмарку"]))
async def choose_fair_handler(message: types.Message) -> None:
    if not message.from_user or message.from_user.id not in ALLOWED_USERS:
        return

    user_id = message.from_user.id
    if not message.text:
        return

    current_fair = await asyncio.to_thread(db_get_user_fair, user_id)

    if message.text == "🔙 Сменить ярмарку":
        if current_fair and await asyncio.to_thread(db_shift_is_open, current_fair):
            # Проверяем, есть ли у пользователя продажи в текущей смене
            my_sales = await asyncio.to_thread(read_my_sales_sync, current_fair, user_id)
            has_sales = my_sales and (
                bool(my_sales['my_items']['items']) or bool(my_sales['by_owner'])
            )
            if has_sales:
                kb = await get_products_kb()
                await message.answer(
                    "⚠️ У вас есть продажи в текущей смене.\nСменить ярмарку можно только после закрытия смены.",
                    reply_markup=kb
                )
                return

        await asyncio.to_thread(db_remove_user_fair, user_id)
        await message.answer("Выберите ярмарку:", reply_markup=get_choose_fair_kb())
        return

    fair_name = message.text.replace("🎪 ", "").replace("🌿 ", "")
    other_fair = "Ecolocal" if fair_name == "Yardsale" else "Yardsale"

    if await asyncio.to_thread(db_shift_is_open, fair_name):
        kb = get_join_or_switch_kb(fair_name, other_fair)
        await message.answer(
            f"⚠️ Смена на <b>{fair_name}</b> уже открыта.\n\n"
            f"Вы можете присоединиться к <b>{fair_name}</b>\n"
            f"или открыть смену на <b>{other_fair}</b>.",
            reply_markup=kb, parse_mode="HTML")
        return

    await asyncio.to_thread(db_set_user_fair, user_id, fair_name)
    logger.info(f"Действие: Выбор ярмарки {fair_name}. Пользователь: {message.from_user.first_name} ({user_id})")

    if await asyncio.to_thread(db_shift_is_open, other_fair):
        await message.answer(
            f"📍 Выбрана ярмарка <b>{fair_name}</b>.\n"
            f"💡 На <b>{other_fair}</b> уже идёт смена. Можете присоединиться к ней позже.",
            parse_mode="HTML")

    await message.answer(f"📍 Ярмарка <b>{fair_name}</b>.\nСмена закрыта. Нажмите ниже, чтобы начать работу:",
                         reply_markup=get_start_kb(), parse_mode="HTML")


@router.message(F.text.startswith("✅ Присоединиться к "))
async def join_open_shift(message: types.Message) -> None:
    if not message.from_user or message.from_user.id not in ALLOWED_USERS or not message.text:
        return

    fair_name = message.text.replace("✅ Присоединиться к ", "")
    await asyncio.to_thread(db_set_user_fair, message.from_user.id, fair_name)
    kb = await get_products_kb()
    await message.answer(f"📍 Вы присоединились к <b>{fair_name}</b>. Можете пробивать чеки:",
                         reply_markup=kb, parse_mode="HTML")


@router.message(F.text.startswith("🔄 Открыть "))
async def open_other_fair(message: types.Message) -> None:
    if not message.from_user or message.from_user.id not in ALLOWED_USERS or not message.text:
        return

    user_id = message.from_user.id
    fair_name = message.text.replace("🔄 Открыть ", "")
    await asyncio.to_thread(db_set_user_fair, user_id, fair_name)

    async with get_fair_lock(fair_name):
        if await asyncio.to_thread(db_shift_is_open, fair_name):
            kb = await get_products_kb()
            await message.answer(f"⚠️ Смена на {fair_name} уже открыта кем-то другим! Вы присоединены.",
                                 reply_markup=kb)
            return

        await asyncio.to_thread(db_open_shift, fair_name, user_id, datetime.now().isoformat())
        await asyncio.to_thread(init_shift_sync, fair_name)
        logger.info(f"Действие: Открыта смена на {fair_name}. Пользователь: {message.from_user.first_name} ({user_id})")

    kb = await get_products_kb()
    await message.answer(f"✅ Вы открыли смену на <b>{fair_name}</b>! Успешных продаж.",
                         reply_markup=kb, parse_mode="HTML")

    for u_id in ALLOWED_USERS:
        if u_id != user_id:
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
                logger.error(f"Failed to notify user {u_id}: {e}")
