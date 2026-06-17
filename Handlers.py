from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from Storage import Storage
from AuthFlow import build_flow, get_authorization_url, exchange_code_for_credentials
from Config import GC_CREDENTIALS_PATH, TZ
from CalendarApi import list_calendars, list_events_for_date, get_primary_timezone
from WeatherApi import get_weather_detailed
import json
from datetime import datetime, timezone as dt_timezone, timedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo

db: Storage = None
user_flows = {}

def get_local_timezone(tz_name: str):
    try:
        return ZoneInfo(tz_name)
    except:
        return dt_timezone(timedelta(hours=3))  # fallback МСК

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Сегодня", callback_data='today')],
        [InlineKeyboardButton("📋 История", callback_data='history')],
        [InlineKeyboardButton("⚙️ Настройки", callback_data='settings')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')],
    ])

def settings_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Уведомления", callback_data='notif')],
        [InlineKeyboardButton("🏙 Город", callback_data='city')],
        [InlineKeyboardButton("🔙 Главное меню", callback_data='main_menu')],
    ])

def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='settings')]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот‑помощник:\n"
        "• Напоминания о встречах из Google Календаря\n"
        "• Прогноз погоды\n\n"
        "Для начала работы авторизуйтесь: /authorize",
        reply_markup=main_keyboard()
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Доступные действия:\n"
        "/authorize – подключить Google Календарь\n"
        "Кнопка «Сегодня» – встречи на сегодня\n"
        "Кнопка «История» – последние 10 встреч\n"
        "Кнопка «Настройки» – управление городом и уведомлениями",
        reply_markup=main_keyboard()
    )

async def authorize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        flow = build_flow(GC_CREDENTIALS_PATH, redirect_uri='http://localhost:8080')
        auth_url, state = get_authorization_url(flow)
        user_flows[user_id] = flow
        await update.message.reply_text(
            "🌐 Перейдите по ссылке и разрешите доступ:\n\n"
            f"{auth_url}\n\n"
            "После разрешения скопируйте **всю ссылку** из адресной строки "
            "(начинается с http://localhost:8080/...) и отправьте её сюда."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_flows:
        return
    flow = user_flows.pop(user_id)
    text = update.message.text.strip()
    code = None
    if text.startswith('http://localhost:8080/'):
        try:
            parsed = urlparse(text)
            params = parse_qs(parsed.query)
            code = params.get('code', [None])[0]
        except:
            pass
    if not code:
        code = text
    if not code:
        await update.message.reply_text("❌ Не удалось извлечь код. Попробуйте ещё раз /authorize.")
        return
    try:
        credentials = exchange_code_for_credentials(flow, code)
        db.upsert_user(user_id, credentials_json=credentials.to_json())
        await update.message.reply_text(
            "✅ Авторизация успешна! Хотите установить город для прогноза погоды? "
            "Отправьте его название (например, Москва,RU):"
        )
        context.user_data['awaiting_city'] = True
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка обмена кода: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    user = db.get_user(user_id)
    if not user or not user.get('credentials_json'):
        await query.edit_message_text("⛔ Сначала авторизуйтесь через /authorize.")
        return

    if data == 'today':
        await show_today(query, user)
    elif data == 'history':
        await show_history(query, user)
    elif data == 'settings':
        await query.edit_message_text("⚙️ Настройки:", reply_markup=settings_keyboard())
    elif data == 'main_menu':
        await query.edit_message_text("Главное меню:", reply_markup=main_keyboard())
    elif data == 'notif':
        await notif_settings(query, user)
    elif data == 'city':
        await query.edit_message_text("Введите город и страну (например: Москва):")
        context.user_data['awaiting_city'] = True
    elif data == 'enable_notif':
        db.upsert_user(user_id, reminder_minutes=30)
        await query.edit_message_text("🔔 Уведомления включены (за 30 мин).", reply_markup=back_keyboard())
    elif data == 'disable_notif':
        db.upsert_user(user_id, reminder_minutes=0)
        await query.edit_message_text("🔕 Уведомления отключены.", reply_markup=back_keyboard())
    elif data.startswith('set_reminder_'):
        minutes = int(data.split('_')[2])
        db.upsert_user(user_id, reminder_minutes=minutes)
        await query.edit_message_text(f"✅ Напоминание за {minutes} мин.", reply_markup=back_keyboard())
    elif data == 'custom_reminder':
        await query.edit_message_text("Введите количество минут (1–720):")
        context.user_data['awaiting_reminder'] = True
    elif data.startswith('mute_'):
        action, event_id = data.split('_', 1)
        mute = action == 'mute'
        db.toggle_mute_event(user_id, event_id, mute)
        await query.answer(f"Уведомление {'отключено' if mute else 'включено'} для этой встречи.", show_alert=True)
        await show_today(query, db.get_user(user_id))
    elif data == 'refresh':
        await show_today(query, db.get_user(user_id))

async def show_today(query, user):
    try:
        creds = Credentials.from_authorized_user_info(json.loads(user['credentials_json']))
        service = build('calendar', 'v3', credentials=creds)
        tz_name = get_primary_timezone(service) or TZ
        local_tz = get_local_timezone(tz_name)
        calendars = list_calendars(service)
        all_events = []
        for cal in calendars:
            events = list_events_for_date(service, calendar_id=cal['id'], timezone_str=tz_name)
            for e in events:
                start_str = e['start'].get('dateTime', e['start'].get('date'))
                start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                local_dt = start_dt.astimezone(local_tz)
                time_str = local_dt.strftime('%H:%M')
                title = e.get('summary', 'Без названия')
                link = e.get('htmlLink', '')
                cal_name = cal['summary']
                event_id = e['id']
                all_events.append((time_str, title, link, cal_name, event_id))
        if not all_events:
            await query.edit_message_text("Что то тут пустовато :( Может чего нибудь запланируете? :)", reply_markup=main_keyboard())
            return
        all_events.sort(key=lambda x: x[0])
        lines = []
        keyboard_rows = []
        for time_str, title, link, cal_name, event_id in all_events:
            line = f"• {time_str} — {title}"
            if cal_name != 'primary':
                line += f" ({cal_name})"
            lines.append(line)
            # Кнопка "Открыть" и переключение mute
            mute_button = InlineKeyboardButton(
                "🔕 Не уведомлять" if not db.is_event_muted(query.from_user.id, event_id) else "🔔 Уведомлять",
                callback_data=f"{'mute' if not db.is_event_muted(query.from_user.id, event_id) else 'unmute'}_{event_id}"
            )
            link_button = InlineKeyboardButton("📅 Открыть в календаре", url=link) if link else None
            row = [link_button, mute_button] if link_button else [mute_button]
            keyboard_rows.append(row)
        text = "📅 Встречи на сегодня:\n" + "\n".join(lines)
        keyboard_rows.append([InlineKeyboardButton("🔄 Обновить", callback_data='refresh')])
        markup = InlineKeyboardMarkup(keyboard_rows)
        await query.edit_message_text(text, reply_markup=markup)
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def show_history(query, user):
    records = db.get_last_history(query.from_user.id)
    if not records:
        await query.edit_message_text("📭 История пуста.", reply_markup=main_keyboard())
        return
    lines = [f"{i+1}. [{r['end_time'][:10]}] {r.get('title','')}" for i,r in enumerate(records)]
    await query.edit_message_text("Последние 10 встреч:\n" + "\n".join(lines), reply_markup=main_keyboard())

async def notif_settings(query, user):
    minutes = user.get('reminder_minutes', 30)
    status = "🔕 Уведомления отключены" if minutes == 0 else f"🔔 Уведомления за {minutes} мин."
    kb = [
        [InlineKeyboardButton("✅ Включить (30 мин)", callback_data='enable_notif')],
        [InlineKeyboardButton("❌ Отключить", callback_data='disable_notif')],
        [InlineKeyboardButton("⚡ 5 мин", callback_data='set_reminder_5')],
        [InlineKeyboardButton("🕐 15 мин", callback_data='set_reminder_15')],
        [InlineKeyboardButton("🕒 30 мин", callback_data='set_reminder_30')],
        [InlineKeyboardButton("🕓 1 час", callback_data='set_reminder_60')],
        [InlineKeyboardButton("🕔 2 часа", callback_data='set_reminder_120')],
        [InlineKeyboardButton("🕖 3 часа", callback_data='set_reminder_180')],
        [InlineKeyboardButton("🔢 Свой вариант", callback_data='custom_reminder')],
        [InlineKeyboardButton("🔙 Назад", callback_data='settings')],
    ]
    await query.edit_message_text(f"{status}\nВыберите действие:", reply_markup=InlineKeyboardMarkup(kb))

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.user_data.get('awaiting_city'):
        city_raw = update.message.text.strip()
        if ',' in city_raw:
            city, country = city_raw.split(',', 1)
            city, country = city.strip(), country.strip()
        else:
            city, country = city_raw, None
        db.upsert_user(user_id, city=city, country=country)
        await update.message.reply_text(f"✅ Город сохранён: {city}" + (f", {country}" if country else ""))
        context.user_data.pop('awaiting_city', None)
        return
    if context.user_data.get('awaiting_reminder'):
        try:
            mins = int(update.message.text.strip())
            if 1 <= mins <= 720:
                db.upsert_user(user_id, reminder_minutes=mins)
                await update.message.reply_text(f"✅ Напоминание за {mins} мин.", reply_markup=settings_keyboard())
            else:
                await update.message.reply_text("⚠️ Введите число от 1 до 720.")
                return
        except ValueError:
            await update.message.reply_text("⚠️ Пожалуйста, введите целое число минут.")
            return
        context.user_data.pop('awaiting_reminder', None)
        return
    await receive_code(update, context)

def setup_handlers(storage_instance: Storage):
    global db
    db = storage_instance
    return [
        CommandHandler("start", start),
        CommandHandler("help", help_cmd),
        CommandHandler("authorize", authorize),
        CallbackQueryHandler(button_handler),
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler),
    ]