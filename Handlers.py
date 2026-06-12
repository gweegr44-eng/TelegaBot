from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from Storage import Storage
from AuthFlow import build_flow, get_authorization_url, exchange_code_for_credentials
from Config import GC_CREDENTIALS_PATH
from WeatherApi import get_weather

db: Storage = None
user_flows = {}

async def ensure_calendar_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user or not user.get('credentials_json'):
        await update.message.reply_text(
            "⛔ Для этой команды нужна авторизация Google Calendar.\n"
            "Используйте /authorize, чтобы предоставить доступ."
        )
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот с функциями:\n"
        "• Напоминания о встречах из Google Calendar\n"
        "• Просмотр погоды\n\n"
        "Для начала авторизуйтесь в календаре: /authorize\n"
        "Для настройки города погоды: /setcity <город>,<код страны>\n"
        "Остальные команды: /help"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Доступные команды:\n"
        "/authorize – авторизация Google Calendar\n"
        "/set_reminder <минуты> – за сколько минут до встречи уведомлять\n"
        "/history – последние 10 встреч\n"
        "/setcity <город,страна> – установить город для погоды\n"
        "/weather – текущая погода\n"
        "/help – эта справка"
    )

async def authorize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        flow = build_flow(GC_CREDENTIALS_PATH, redirect_uri='urn:ietf:wg:oauth:2.0:oob')
        auth_url, state = get_authorization_url(flow)
        user_flows[user_id] = flow
        await update.message.reply_text(
            "🌐 Перейдите по ссылке и разрешите доступ к календарю:\n\n"
            f"{auth_url}\n\n"
            "После этого скопируйте полученный код и отправьте его сюда одним сообщением."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_flows:
        return
    flow = user_flows.pop(user_id)
    code = update.message.text.strip()
    try:
        credentials = exchange_code_for_credentials(flow, code)
        db.upsert_user(user_id, credentials_json=credentials.to_json())
        await update.message.reply_text("✅ Авторизация успешна! Теперь я могу следить за вашим календарём.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка обмена кода: {e}")

async def set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_calendar_auth(update, context):
        return
    user_id = update.effective_user.id
    try:
        minutes = int(context.args[0])
        if minutes < 1 or minutes > 120:
            raise ValueError
    except:
        await update.message.reply_text("⏰ Используйте: /set_reminder <минуты от 1 до 120>")
        return
    db.upsert_user(user_id, reminder_minutes=minutes)
    await update.message.reply_text(f"✅ Уведомления будут за {minutes} мин. до встречи.")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_calendar_auth(update, context):
        return
    user_id = update.effective_user.id
    records = db.get_last_history(user_id)
    if not records:
        await update.message.reply_text("📭 История встреч пуста.")
        return
    lines = []
    for i, rec in enumerate(records, 1):
        end_time = rec['end_time'][:10]
        title = rec.get('title', 'Без названия')
        lines.append(f"{i}. [{end_time}] {title}")
    await update.message.reply_text("Последние 10 встреч:\n" + "\n".join(lines))

async def set_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(
            "Укажите город и страну через запятую.\n"
            "Пример: /setcity Москва,RU\n"
            "Или только город: /setcity London"
        )
        return
    raw = ' '.join(context.args)
    if ',' in raw:
        parts = raw.split(',', 1)
        city = parts[0].strip()
        country = parts[1].strip()
    else:
        city = raw.strip()
        country = None
    if not city:
        await update.message.reply_text("Город не может быть пустым.")
        return
    db.upsert_user(user_id, city=city, country=country)
    reply = f"✅ Город установлен: {city}"
    if country:
        reply += f", {country}"
    await update.message.reply_text(reply)

async def weather_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user or not user.get('city'):
        await update.message.reply_text("Сначала установите город командой /setcity")
        return
    city = user['city']
    country = user.get('country')
    msg = get_weather(city, country)
    await update.message.reply_text(msg)

def setup_handlers(storage_instance: Storage):
    global db
    db = storage_instance
    return [
        CommandHandler("start", start),
        CommandHandler("help", help_cmd),
        CommandHandler("authorize", authorize),
        CommandHandler("set_reminder", set_reminder),
        CommandHandler("history", history),
        CommandHandler("setcity", set_city),
        CommandHandler("weather", weather_cmd),
        MessageHandler(filters.TEXT & ~filters.COMMAND, receive_code),
    ]