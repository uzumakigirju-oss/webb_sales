# 🚀 Руководство по запуску проекта Omnom & SweetMe

## ✅ Статус готовности

```
✅ Все зависимости установлены
✅ Веб-приложение загружается (25 маршрутов)
✅ Telegram бот загружается (5 обработчиков)
✅ CORS настроен
✅ CSV парсинг улучшен
✅ .gitignore создан
```

---

## ⚠️ КРИТИЧЕСКИ ВАЖНО: Регенерируйте BOT_TOKEN

Текущий `BOT_TOKEN` в `.env` **компрометирован** (виден в кодовой базе).

### Как регенерировать:

1. Откройте Telegram
2. Найдите **@BotFather**
3. Отправьте `/start`
4. Нажмите на вашего бота (sweetme_omnom_day_bot)
5. Выберите "Edit Bot" → "Edit Tokens"
6. Скопируйте новый токен
7. Обновите `.env`:
   ```
   BOT_TOKEN=<НОВЫЙ_ТОКЕН>
   PRODUCTS_FILE=products.csv
   WEB_APP_URL=https://uzumakigirju-oss.github.io/kassa-app/
   BASE_URL=http://localhost:8000
   ```

---

## 🎯 Быстрый старт

### 1️⃣ Откройте 3 терминала

#### Терминал 1: Telegram бот
```bash
cd /Users/admin/Desktop/test
python3 main.py
```
Должен вывести:
```
2026-06-16 21:30:45,123 - root - INFO - Initializing SQLite database...
2026-06-16 21:30:45,124 - root - INFO - Starting Telegram bot polling...
```

#### Терминал 2: Веб-приложение
```bash
cd /Users/admin/Desktop/test
python3 -m uvicorn web_app:app --host 0.0.0.0 --port 8000
```
Должен вывести:
```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
```

#### Терминал 3: Проверка
```bash
# Проверьте, что всё работает
curl http://localhost:8000/api/auth/me

# Должен вернуть (если не авторизован):
# {"authenticated": false}
```

---

## 🌐 Доступ к приложению

1. **Веб-касса**: http://localhost:8000
2. **Telegram**: @sweetme_omnom_day_bot
3. **API Docs**: http://localhost:8000/docs (Swagger UI)

---

## 📝 Что было исправлено

| Проблема | Решение |
|----------|---------|
| Отсутствует `python-multipart` | ✅ Установлена из `requirements.txt` |
| Отсутствует `httpx` и другие зависимости | ✅ Все установлены |
| CORS не настроен | ✅ Добавлен `CORSMiddleware` |
| CSV парсинг падает на пробелы | ✅ Улучшена обработка в `sales_manager.py` |
| Нет `.gitignore` | ✅ Создан с нужными исключениями |
| BOT_TOKEN скомпрометирован | ⚠️ **ТРЕБУЕТ РЕГЕНЕРАЦИИ** |

---

## 🔐 Список разрешённых пользователей

```python
ALLOWED_USERS = {
    141076129: "Нина",
    330619718: "Александр",
    4013760: "Анна"
}
```

Только эти пользователи имеют доступ к кассе.

---

## 📊 Структура данных

### SQLite (`bot_state.db`)
```sql
-- Текущий выбор ярмарки пользователем
active_fairs (user_id, fair_name)

-- Открытые смены
shifts (fair_name, owner_id, opened_at)
```

### CSV файлы
```
# Во время смены
sales_yardsale.csv / sales_ecolocal.csv

# После закрытия смены (архив)
archives/2026/06/sales_yardsale_2026-06-16_21-30-45.csv
```

### Загруженные файлы
```
shared_files/          # Хранилище файлов
shared_files.json      # Метаданные
```

---

## 🎨 Вкладки приложения

### 1. 🛒 Касса (POS)
- Выбор товаров
- Управление корзиной
- Выбор способа оплаты (наличные/карта)
- Фильтры по владельцу товара

### 2. 📊 Статистика
- Личная статистика (мои продажи)
- Общая статистика (все продажи на ярмарке)
- Разбор по товарам и типам оплаты

### 3. 📁 Файлы
- Загрузка файлов
- Общий доступ для команды
- История загрузок

---

## 🐛 Если что-то пошло не так

### Ошибка: `ModuleNotFoundError: No module named 'httpx'`
```bash
python3 -m pip install -r requirements.txt
```

### Ошибка: `RuntimeError: Form data requires "python-multipart"`
```bash
python3 -m pip install python-multipart
```

### Ошибка: `Telegram API error: 401`
- Проверьте, что обновили `.env` с новым BOT_TOKEN

### Ошибка: `sqlite3.OperationalError: database is locked`
- Убедитесь, что не запущено 2 экземпляра main.py одновременно

### Ошибка: `Connection refused` при подключении к http://localhost:8000
- Убедитесь, что веб-приложение запущено во втором терминале

---

## 📚 Полезные команды

```bash
# Просмотр логов бота
tail -f bot.log

# Просмотр содержимого products.csv
cat products.csv | head -10

# Проверка CSV продаж (во время смены)
cat sales_yardsale.csv

# Просмотр архивированных отчётов
ls archives/2026/06/

# Перезагрузка базы данных (ВНИМАНИЕ!)
rm bot_state.db  # Будет создана новая при запуске
```

---

## 🎯 Workflow кассира

1. **Начало смены:**
   - Нажать "Начать смену" в боте или веб-приложении
   - Выбрать ярмарку (Yardsale / Ecolocal)

2. **Во время смены:**
   - Выбирать товары и добавлять в корзину
   - Выбирать способ оплаты
   - Просматривать статистику

3. **Конец смены:**
   - Нажать "Закрыть день"
   - Подтвердить закрытие
   - Автоматически генерируется отчёт с архивированием

---

## 📞 Поддержка

В случае ошибок смотрите:
- `bot.log` — логи Telegram бота
- `ERROR_REPORT.md` — подробный анализ проблем
- `requirements.txt` — версии зависимостей

---

## ✨ Успешно!

После выполнения всех шагов приложение должно работать полностью.

**Удачи с продажами! 🧁**
