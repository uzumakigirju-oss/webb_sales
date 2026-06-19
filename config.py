import os
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не установлена в .env файле")

PRODUCTS_FILE = os.getenv("PRODUCTS_FILE", "products.csv")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://uzumakigirju-oss.github.io/kassa-app/")

ALLOWED_USERS = {
    141076129: "Нина",
    330619718: "Александр",
    4013760: "Анна"
}

CURRENT_URL_FILE = ".current_url"

def get_web_app_url() -> str:
    try:
        if os.path.exists(CURRENT_URL_FILE):
            with open(CURRENT_URL_FILE, "r") as f:
                url = f.read().strip()
                if url:
                    return url
    except Exception:
        pass
    return WEB_APP_URL