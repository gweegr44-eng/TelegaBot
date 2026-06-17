from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from Storage import Storage
from AuthFlow import build_flow, get_authorization_url, exchange_code_for_credentials
from Config import GC_CREDENTIALS_PATH, TZ, ADMIN_ID
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
        return dt_timezone(timedelta(hours=3))

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Сегодня", callback_data='today')],
        [InlineKeyboardButton("📋 История", callback_data='history')],
        [InlineKeyboardButton("⚙️ Настройки", callback_data='settings')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help_main')],
    ])

def auth_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Авторизоваться", callback_data='start_auth')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help_auth')],
    ])

def skip_city_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭ Пропустить", callback_data='skip_city')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help_city_setup')],
    ])

def settings_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Уведомления", callback_data='notif')],
        [InlineKeyboardButton("🏙 Город", callback_data='city')],
        [InlineKeyboardButton("🚪 Выйти", callback_data='logout')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help_settings')],
        [InlineKeyboardButton("🔙 Главное меню", callback_data='main_menu')],
    ])

def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='settings')]])

def help_back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Вернуться", callback_data='back_from_help')]
    ])

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Пользователи", callback_data='admin_users')],
        [InlineKeyboardButton("📨 Отправить сообщение", callback_data='admin_send')],
        [InlineKeyboardButton("📋 Лог пользователя", callback_data='admin_log')],
        [InlineKeyboardButton("🔙 Закрыть", callback_data='main_menu')],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if user and user.get('credentials_json'):
        await update.message.reply_text(
            "👋 Привет! Я бот‑помощник:\n"
            "• Напоминания о встречах из Google Календаря\n"
            "• Прогноз погоды\n\n"
            "Вы уже авторизованы. Используйте меню:",
            reply_markup=main_keyboard()
        )
    else:
        await update.message.reply_text(
            "👋 Привет! Я бот‑помощник:\n"
            "• Напоминания о встречах из Google Календаря\n"
            "• Прогноз погоды\n\n"
            "Для начала работы нужно авторизоваться в Google Календаре.",
            reply_markup=auth_keyboard()
        )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    kb = main_keyboard() if (user and user.get('credentials_json')) else auth_keyboard()
    await update.message.reply_text(
        "Доступные действия:\n"
        "• Авторизация через кнопку или команду /authorize\n"
        "• «Сегодня» – встречи на сегодня\n"
        "• «История» – последние 10 встреч\n"
        "• «Настройки» – управление городом и уведомлениями\n"
        "• «Выйти» – сбросить авторизацию",
        reply_markup=kb
    )

async def authorize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_auth_callback(update, context)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Недостаточно прав.")
        return
    await update.message.reply_text(
        "🛠 Админ-панель\nВыберите действие:",
        reply_markup=admin_keyboard()
    )

async def start_auth_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        target = query.message
        user_id = query.from_user.id
    else:
        target = update.message
        user_id = update.effective_user.id

    try:
        flow = build_flow(GC_CREDENTIALS_PATH, redirect_uri='http://localhost:8080')
        auth_url, state = get_authorization_url(flow)
        user_flows[user_id] = flow
        text = (
            "🌐 Перейдите по ссылке и разрешите доступ:\n\n"
            f"{auth_url}\n\n"
            "После разрешения скопируйте **всю ссылку** из адресной строки "
            "(начинается с http://localhost:8080/...) и отправьте её сюда."
        )
        if query:
            await query.edit_message_text(text)
        else:
            await target.reply_text(text)
    except Exception as e:
        await target.reply_text(f"❌ Ошибка: {e}")

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
        await update.message.reply_text("❌ Не удалось извлечь код. Попробуйте ещё раз.")
        return
    try:
        credentials = exchange_code_for_credentials(flow, code)
        db.upsert_user(user_id, credentials_json=credentials.to_json())
        context.user_data['awaiting_city'] = True
        await update.message.reply_text(
            "✅ Авторизация успешна!\n\n"
            "Хотите сразу установить город для прогноза погоды? "
            "Отправьте его название (например: Москва) или нажмите кнопку «Пропустить».",
            reply_markup=skip_city_keyboard()
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка обмена кода: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    user = db.get_user(user_id)

    # Помощь и подсказки
    if data == 'help_main':
        context.user_data['help_back'] = 'main'
        await query.edit_message_text(
            "🌟 **Главное меню**\n\n"
            "Здесь ты можешь:\n"
            "• 📅 **Сегодня** – глянуть все встречи на сегодня и при желании отключить напоминалку.\n"
            "• 📋 **История** – увидеть, что уже прошло (вдруг забыл).\n"
            "• ⚙️ **Настройки** – включить/выключить уведомления, сменить город или вообще выйти из аккаунта.\n\n"
            "В любой непонятной ситуации жми «Помощь» – расскажу, что и как.",
            reply_markup=help_back_keyboard(),
            parse_mode='Markdown'
        )
        return
    if data == 'help_auth':
        context.user_data['help_back'] = 'auth'
        await query.edit_message_text(
            "🔑 **Авторизация**\n\n"
            "Боту нужен доступ к твоему Google Календарю, чтобы следить за встречами.\n"
            "Нажми кнопку «Авторизоваться», перейди по ссылке, разреши доступ и отправь мне ссылку из адресной строки.\n"
            "Никакие пароли я не вижу – только встречи!",
            reply_markup=help_back_keyboard(),
            parse_mode='Markdown'
        )
        return
    if data == 'help_settings':
        context.user_data['help_back'] = 'settings'
        await query.edit_message_text(
            "⚙️ **Настройки**\n\n"
            "• 🔔 **Уведомления** – за сколько минут до встречи предупредить (или вообще выключить).\n"
            "• 🏙 **Город** – выбери город для прогноза погоды в напоминаниях.\n"
            "• 🚪 **Выйти** – отвязать Google-аккаунт (можно потом снова авторизоваться).\n\n"
            "Выбирай нужное и настраивай под себя!",
            reply_markup=help_back_keyboard(),
            parse_mode='Markdown'
        )
        return
    if data == 'help_notif':
        context.user_data['help_back'] = 'notif'
        await query.edit_message_text(
            "🔔 **Настройка уведомлений**\n\n"
            "Ты можешь:\n"
            "• Включить уведомления (по умолчанию за 30 мин).\n"
            "• Полностью отключить.\n"
            "• Выбрать готовое время: 5, 15, 30, 60, 120 или 180 минут.\n"
            "• Или задать своё число (от 1 до 720 минут – это 12 часов).\n\n"
            "Чем меньше минут, тем быстрее я тебя предупрежу!",
            reply_markup=help_back_keyboard(),
            parse_mode='Markdown'
        )
        return
    if data == 'help_today':
        context.user_data['help_back'] = 'today'
        await query.edit_message_text(
            "📅 **Встречи на сегодня**\n\n"
            "Это твой дневной план.\n"
            "Около каждой встречи есть кнопки:\n"
            "• 📅 **Открыть в календаре** – посмотреть детали.\n"
            "• 🔕/🔔 **Не уведомлять/Уведомлять** – выключить или включить напоминание для конкретной встречи.\n"
            "Кнопка «🔄 Обновить» перезагрузит список, если ты что-то добавил в календаре.\n\n"
            "Если встреч нет – время расслабиться!",
            reply_markup=help_back_keyboard(),
            parse_mode='Markdown'
        )
        return
    if data == 'help_city_setup':
        context.user_data['help_back'] = 'city_setup'
        await query.edit_message_text(
            "🏙 **Установка города**\n\n"
            "Введи название города (можно с кодом страны, например: Москва,RU).\n"
            "Я запомню его и буду добавлять прогноз погоды к каждому напоминанию.\n"
            "Если не хочешь – нажми «Пропустить».\n\n"
            "Позже город можно сменить в Настройках.",
            reply_markup=help_back_keyboard(),
            parse_mode='Markdown'
        )
        return
    if data == 'help_history':
        context.user_data['help_back'] = 'history'
        await query.edit_message_text(
            "📋 **История встреч**\n\n"
            "Здесь хранятся последние 10 завершённых встреч.\n"
            "Удобно, если нужно быстро вспомнить, что было.\n"
            "Новые встречи попадают сюда автоматически, как только заканчиваются.",
            reply_markup=help_back_keyboard(),
            parse_mode='Markdown'
        )
        return
    if data == 'back_from_help':
        back_to = context.user_data.pop('help_back', 'main')
        if back_to == 'main':
            await query.edit_message_text(
                "🌟 Главное меню\nЧто будем делать?",
                reply_markup=main_keyboard()
            )
        elif back_to == 'auth':
            await query.edit_message_text(
                "👋 Привет! Я бот‑помощник:\n"
                "• Напоминания о встречах из Google Календаря\n"
                "• Прогноз погоды\n\n"
                "Для начала работы нужно авторизоваться в Google Календаре.",
                reply_markup=auth_keyboard()
            )
        elif back_to == 'settings':
            await query.edit_message_text("⚙️ Настройки:", reply_markup=settings_keyboard())
        elif back_to == 'notif':
            await notif_settings(query, user)
        elif back_to == 'today':
            await show_today(query, user)
        elif back_to == 'history':
            await show_history(query, user)
        elif back_to == 'city_setup':
            await query.edit_message_text(
                "✅ Авторизация успешна!\n\n"
                "Хотите сразу установить город для прогноза погоды? "
                "Отправьте его название (например: Москва) или нажмите кнопку «Пропустить».",
                reply_markup=skip_city_keyboard()
            )
        return

    # Навигация
    if data == 'start_auth':
        await start_auth_callback(update, context)
        return
    if data == 'skip_city':
        context.user_data.pop('awaiting_city', None)
        await query.edit_message_text(
            "🌟 Главное меню\nЧто будем делать?",
            reply_markup=main_keyboard()
        )
        return
    if data == 'main_menu':
        if user and user.get('credentials_json'):
            await query.edit_message_text(
                "🌟 Главное меню\nЧто будем делать?",
                reply_markup=main_keyboard()
            )
        else:
            await query.edit_message_text(
                "🔒 Для доступа к меню нужна авторизация.",
                reply_markup=auth_keyboard()
            )
        return

    # Админские (только ADMIN_ID)
    if user_id == ADMIN_ID:
        if data == 'admin_users':
            users = db.get_all_users_list()
            if not users:
                await query.edit_message_text("Пока нет пользователей.", reply_markup=admin_keyboard())
                return
            kb = []
            for u in users:
                uid = u['user_id']
                kb.append([InlineKeyboardButton(f"👤 {uid}", callback_data=f'admin_user_{uid}')])
            kb.append([InlineKeyboardButton("🔙 Назад", callback_data='admin')])
            await query.edit_message_text("Список пользователей (user_id):", reply_markup=InlineKeyboardMarkup(kb))
            return
        if data.startswith('admin_user_'):
            uid = int(data.split('_')[2])
            user_info = db.get_user(uid)
            if user_info:
                city = user_info.get('city', '—')
                text = f"👤 Пользователь `{uid}`\nГород: {city}\nУведомления: {user_info.get('reminder_minutes', '—')} мин."
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📨 Отправить сообщение", callback_data=f'admin_send_to_{uid}')],
                    [InlineKeyboardButton("📋 Лог сообщений", callback_data=f'admin_log_{uid}')],
                    [InlineKeyboardButton("🔙 Назад", callback_data='admin_users')],
                ])
                await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
            else:
                await query.answer("Пользователь не найден.")
            return
        if data.startswith('admin_send_to_'):
            uid = int(data.split('_')[3])
            context.user_data['admin_recipient'] = uid
            context.user_data['awaiting_admin_message'] = True
            await query.edit_message_text(f"Введите текст сообщения для пользователя `{uid}`:", parse_mode='Markdown')
            return
        if data == 'admin_send':
            await query.edit_message_text("Введите ID получателя (user_id):")
            context.user_data['awaiting_admin_recipient'] = True
            return
        if data.startswith('admin_log_'):
            uid = int(data.split('_')[2])
            logs = db.get_user_logs(uid, 20)
            if not logs:
                await query.edit_message_text(f"У пользователя `{uid}` нет логов.", parse_mode='Markdown',
                                              reply_markup=admin_keyboard())
                return
            lines = [f"{l['timestamp'][:16]} – {l['text'][:100]}" for l in logs]
            text = f"📋 Последние сообщения от `{uid}`:\n" + "\n".join(lines)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data=f'admin_user_{uid}')]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
            return
        if data == 'admin_log':
            await query.edit_message_text("Введите ID пользователя для просмотра лога:")
            context.user_data['awaiting_admin_log_id'] = True
            return

    if not user or not user.get('credentials_json'):
        await query.edit_message_text(
            "⛔ Сначала нужно авторизоваться. Нажмите кнопку ниже.",
            reply_markup=auth_keyboard()
        )
        return

    if data == 'today':
        await show_today(query, user)
    elif data == 'history':
        await show_history(query, user)
    elif data == 'settings':
        await query.edit_message_text("⚙️ Настройки:", reply_markup=settings_keyboard())
    elif data == 'notif':
        await notif_settings(query, user)
    elif data == 'city':
        await query.edit_message_text("Введите название города (можно с кодом страны, например: Москва,RU):")
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
        try:
            await show_today(query, db.get_user(user_id))
        except Exception as e:
            if "Message is not modified" in str(e):
                await query.answer("Список уже актуален.", show_alert=True)
            else:
                raise
    elif data == 'logout':
        db.upsert_user(user_id, credentials_json=None, muted_events=None)
        await query.edit_message_text(
            "👋 Вы вышли из аккаунта. Чтобы снова использовать календарь, авторизуйтесь.",
            reply_markup=auth_keyboard()
        )

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
            mute_button = InlineKeyboardButton(
                "🔕 Не уведомлять" if not db.is_event_muted(query.from_user.id, event_id) else "🔔 Уведомлять",
                callback_data=f"{'mute' if not db.is_event_muted(query.from_user.id, event_id) else 'unmute'}_{event_id}"
            )
            link_button = InlineKeyboardButton("📅 Открыть в календаре", url=link) if link else None
            row = [link_button, mute_button] if link_button else [mute_button]
            keyboard_rows.append(row)
        text = "📅 Встречи на сегодня:\n" + "\n".join(lines)
        keyboard_rows.append([
            InlineKeyboardButton("🔄 Обновить", callback_data='refresh'),
            InlineKeyboardButton("🏠 В меню", callback_data='main_menu'),
            InlineKeyboardButton("❓ Помощь", callback_data='help_today')
        ])
        markup = InlineKeyboardMarkup(keyboard_rows)
        await query.edit_message_text(text, reply_markup=markup)
    except Exception as e:
        if "Message is not modified" not in str(e):
            await query.edit_message_text(f"❌ Ошибка: {e}")

async def show_history(query, user):
    records = db.get_last_history(query.from_user.id)
    if not records:
        await query.edit_message_text("📭 История пуста.", reply_markup=main_keyboard())
        return
    lines = [f"{i+1}. [{r['end_time'][:10]}] {r.get('title','')}" for i,r in enumerate(records)]
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 В меню", callback_data='main_menu'),
         InlineKeyboardButton("❓ Помощь", callback_data='help_history')]
    ])
    await query.edit_message_text("Последние 10 встреч:\n" + "\n".join(lines), reply_markup=keyboard)

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
        [InlineKeyboardButton("❓ Помощь", callback_data='help_notif'),
         InlineKeyboardButton("🔙 Назад", callback_data='settings')],
    ]
    await query.edit_message_text(f"{status}\nВыберите действие:", reply_markup=InlineKeyboardMarkup(kb))

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    db.add_user_log(user_id, text)

    if user_id == ADMIN_ID:
        if context.user_data.get('awaiting_admin_recipient'):
            try:
                recipient_id = int(text)
            except ValueError:
                await update.message.reply_text("⚠️ Введите числовой ID.")
                return
            context.user_data['admin_recipient'] = recipient_id
            context.user_data.pop('awaiting_admin_recipient', None)
            context.user_data['awaiting_admin_message'] = True
            await update.message.reply_text(f"ID получателя `{recipient_id}` сохранён. Введите текст сообщения:", parse_mode='Markdown')
            return
        if context.user_data.get('awaiting_admin_message'):
            recipient_id = context.user_data.get('admin_recipient')
            if recipient_id:
                try:
                    await update.message.bot.send_message(chat_id=recipient_id, text=text)
                    await update.message.reply_text("✅ Сообщение отправлено.")
                except Exception as e:
                    await update.message.reply_text(f"❌ Ошибка отправки: {e}")
                context.user_data.pop('admin_recipient', None)
                context.user_data.pop('awaiting_admin_message', None)
            else:
                await update.message.reply_text("Сначала укажите ID получателя через админ-панель.")
            return
        if context.user_data.get('awaiting_admin_log_id'):
            try:
                uid = int(text)
            except ValueError:
                await update.message.reply_text("⚠️ Введите числовой ID.")
                return
            logs = db.get_user_logs(uid, 20)
            if not logs:
                await update.message.reply_text(f"У пользователя `{uid}` нет логов.", parse_mode='Markdown')
            else:
                lines = [f"{l['timestamp'][:16]} – {l['text'][:100]}" for l in logs]
                txt = f"📋 Последние сообщения от `{uid}`:\n" + "\n".join(lines)
                await update.message.reply_text(txt, parse_mode='Markdown')
            context.user_data.pop('awaiting_admin_log_id', None)
            return

    if context.user_data.get('awaiting_city'):
        city_raw = text
        if ',' in city_raw:
            city, country = city_raw.split(',', 1)
            city, country = city.strip(), country.strip()
        else:
            city, country = city_raw, None
        db.upsert_user(user_id, city=city, country=country)
        context.user_data.pop('awaiting_city', None)
        await update.message.reply_text(
            f"✅ Город сохранён: {city}" + (f", {country}" if country else ""),
            reply_markup=main_keyboard()
        )
        return
    if context.user_data.get('awaiting_reminder'):
        try:
            mins = int(text)
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
        CommandHandler("authorize", authorize_command),
        CommandHandler("admin", admin_command),
        CallbackQueryHandler(button_handler),
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler),
    ]