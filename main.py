import asyncio
import logging
import os
import signal
import subprocess
from aiogram import Bot, Dispatcher
from config import API_TOKEN
from database import init_db
from handlers import common_router, shift_router, sales_router, stats_router, files_router

def kill_other_instances():
    current_pid = os.getpid()
    try:
        output = subprocess.check_output(["ps", "-A", "-o", "pid,command"]).decode("utf-8")
        for line in output.splitlines():
            if "main.py" in line and "python" in line.lower():
                parts = line.strip().split(maxsplit=1)
                if len(parts) >= 2:
                    try:
                        pid = int(parts[0])
                        if pid != current_pid:
                            os.kill(pid, signal.SIGTERM)
                            print(f"Killed old bot process (PID: {pid})")
                    except (ValueError, OSError):
                        pass
    except Exception as e:
        print(f"Error checking processes: {e}")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Регистрируем роутеры
dp.include_router(common_router)
dp.include_router(shift_router)
dp.include_router(sales_router)
dp.include_router(stats_router)
dp.include_router(files_router)


async def main() -> None:
    kill_other_instances()
    logger.info("Initializing SQLite database...")
    init_db()
    logger.info("Starting Telegram bot polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")