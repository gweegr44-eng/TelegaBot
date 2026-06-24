# 📅 CalendarWeatherBot — Telegram-бот для встреч и погоды

Telegram-бот, который подключается к Google Calendar, отслеживает встречи, присылает уведомления и показывает прогноз погоды.

## 🚀 Возможности

### Основные функции
- `/start` — приветствие и главное меню с кнопками
- `/authorize` — авторизация в Google Calendar через OAuth 2.0
-  **Сегодня** — список встреч на сегодня с кнопками «Открыть в календаре» и «Не уведомлять»
-  **История** — последние 10 завершённых встреч
-  **Настройки** — уведомления (от 5 мин до 12 часов), выбор города для погоды, выход из аккаунта

### Погода тоже отсебя подумал прикольно
-  Автоматически добавляется к каждому напоминанию
- Температура, ощущается как, описание, влажность, ветер, давление, видимость

### Админ-панель просто добавил от себя
- `/admin` — вход в админ-панель (только для ADMIN_ID из `.env`)
-  Список пользователей с именами
-  Чат с пользователем (текст, стикеры, фото, видео)
-  Логи сообщений пользователей

---

##  Установка и запуск

### 1. Клонируйте репозиторий
```bash
git clone https://github.com/gweegr44-eng/TelegaBot1.git
cd TelegaBot1
2. Установите зависимости
bash
pip install -r requirements.txt
3. Создайте файл .env
ini
TG_BOT_TOKEN=токен_от_BotFather
GC_CREDENTIALS_PATH=credentials.json
DB_PATH=PogodaDB.db
TZ=Europe/Moscow
OWM_API_KEY=ключ_OpenWeatherMap
ADMIN_ID=ваш_telegram_id
4. Получите credentials.json
Перейдите в Google Cloud Console

Создайте проект и включите Google Calendar API

Создайте OAuth 2.0 Client ID (тип: Desktop app)

Скачайте JSON и переименуйте в credentials.json

Положите файл в корень проекта

5. Получите API-ключ погоды
Зарегистрируйтесь на OpenWeatherMap

Скопируйте API-ключ в .env (переменная OWM_API_KEY)

6. Запустите бота
bash
python main.py
🛠 Технологии
Python 3.11+

python-telegram-bot — Telegram Bot API

google-api-python-client — Google Calendar API

APScheduler — фоновый планировщик

OpenWeatherMap API — прогноз погоды

SQLite — база данных

OAuth 2.0 — авторизация Google

 Структура проекта
text
├── main.py              # Точка входа
├── Config.py            # Загрузка переменных окружения
├── Storage.py           # Работа с SQLite
├── AuthFlow.py          # OAuth 2.0 авторизация
├── CalendarApi.py       # Google Calendar API
├── WeatherApi.py        # OpenWeatherMap API
├── Handlers.py          # Обработчики команд и кнопок
├── Scheduler.py         # Фоновые уведомления
├── requirements.txt     # Зависимости
├── .env                 # Переменные окружения (не коммитить)
├── credentials.json     # Ключи Google OAuth (не коммитить)
└── README.md            # Документация
 Безопасность
Токены и ключи хранятся в .env 

credentials.json добавлен в .gitignore

База данных хранится локально

Админ-панель доступна только по Telegram ID