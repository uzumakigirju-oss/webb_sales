import logging
import asyncio
from aiogram import Router, F, types
from config import ALLOWED_USERS
from database import db_get_user_fair

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.photo | F.document)
async def share_file_with_team(message: types.Message) -> None:
    if not message.from_user or message.from_user.id not in ALLOWED_USERS:
        return

    fair_name = await asyncio.to_thread(db_get_user_fair, message.from_user.id) or "Общий чат"
    await message.answer("✅ Файл успешно переслан команде.")

    for user_id in ALLOWED_USERS:
        if user_id != message.from_user.id:
            try:
                await message.bot.send_message(
                    chat_id=user_id,
                    text=f"📎 <b>Новый файл от {message.from_user.first_name}</b> ({fair_name}):",
                    parse_mode="HTML"
                )
                await message.copy_to(chat_id=user_id)
            except Exception as e:
                logger.error(f"Failed to copy file to user {user_id}: {e}")
