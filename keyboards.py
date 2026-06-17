import json
import urllib.parse
from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from config import WEB_APP_URL
from sales_manager import read_products

def get_choose_fair_kb() -> types.ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="🎪 Yardsale")
    builder.button(text="🌿 Ecolocal")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def get_start_kb() -> types.ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="▶️ Начать смену")
    builder.button(text="🔙 Сменить ярмарку")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


async def get_products_kb() -> types.ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    products = await read_products()

    catalog_json = json.dumps(products)
    encoded_catalog = urllib.parse.quote(catalog_json)

    web_app_url = f"{WEB_APP_URL}?v=2&catalog={encoded_catalog}"

    builder.button(text="🛒 Открыть кассу", web_app=WebAppInfo(url=web_app_url))
    builder.adjust(1)
    builder.row(types.KeyboardButton(text="❌ Закрыть день"))
    builder.row(types.KeyboardButton(text="🔙 Сменить ярмарку"))
    return builder.as_markup(resize_keyboard=True)


def get_join_or_switch_kb(open_fair: str, other_fair: str) -> types.ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text=f"✅ Присоединиться к {open_fair}")
    builder.button(text=f"🔄 Открыть {other_fair}")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def get_confirm_close_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, закрыть смену", callback_data="confirm_close")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_close")]
    ])
