import json
from datetime import datetime, timedelta, timezone as dt_timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from Storage import Storage
from CalendarApi import list_upcoming_events, list_calendars, get_primary_timezone
from WeatherApi import get_weather_detailed
from zoneinfo import ZoneInfo
import asyncio

scheduler = BackgroundScheduler()
notified_events = {}
_storage = None
_bot = None

def get_local_timezone(tz_name: str):
    try:
        return ZoneInfo(tz_name)
    except:
        return dt_timezone(timedelta(hours=3))

def start_scheduler(bot, storage: Storage):
    global _storage, _bot
    _storage = storage
    _bot = bot
    scheduler.add_job(lambda: asyncio.new_event_loop().run_until_complete(_reschedule_all()),
                      'interval', minutes=5, id='reschedule')
    scheduler.add_job(lambda: asyncio.new_event_loop().run_until_complete(_check_completed()),
                      'interval', minutes=5, id='history_check')
    scheduler.start()

async def _reschedule_all():
    now = datetime.now(dt_timezone.utc)
    users = _storage.get_all_users_with_credentials()
    for user in users:
        user_id = user['user_id']
        reminder_minutes = user.get('reminder_minutes', 30)
        if reminder_minutes == 0:
            continue
        creds_json = user['credentials_json']
        if not creds_json:
            continue
        try:
            creds = Credentials.from_authorized_user_info(json.loads(creds_json))
            service = build('calendar', 'v3', credentials=creds)
            calendars = list_calendars(service)
            for cal in calendars:
                events = list_upcoming_events(service, calendar_id=cal['id'],
                                              time_min=now.isoformat(),
                                              time_max=(now + timedelta(hours=24)).isoformat())
                for event in events:
                    event_id = event['id']
                    # Проверяем, не заглушен ли этот event
                    if _storage.is_event_muted(user_id, event_id):
                        continue
                    start_str = event['start'].get('dateTime', event['start'].get('date'))
                    start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                    key = f"{user_id}:{cal['id']}:{event_id}"
                    if user_id not in notified_events:
                        notified_events[user_id] = set()
                    if key in notified_events[user_id]:
                        continue
                    notify_time = start_dt - timedelta(minutes=reminder_minutes)
                    if notify_time <= now:
                        await send_reminder(user_id, event, cal['id'], creds_json)
                    else:
                        job_id = f"remind_{user_id}_{event_id}"
                        if not scheduler.get_job(job_id):
                            scheduler.add_job(
                                lambda uid=user_id, ev=event, cid=cal['id'], cr=creds_json:
                                    asyncio.new_event_loop().run_until_complete(send_reminder(uid, ev, cid, cr)),
                                DateTrigger(run_date=notify_time),
                                id=job_id,
                                replace_existing=True
                            )
        except Exception as e:
            print(f"Ошибка планирования user {user_id}: {e}")

async def send_reminder(user_id, event, calendar_id, credentials_json):
    key = f"{user_id}:{calendar_id}:{event['id']}"
    if user_id not in notified_events:
        notified_events[user_id] = set()
    if key in notified_events[user_id]:
        return
    notified_events[user_id].add(key)
    try:
        creds = Credentials.from_authorized_user_info(json.loads(credentials_json))
        service = build('calendar', 'v3', credentials=creds)
        tz_name = get_primary_timezone(service) or 'Europe/Moscow'
        local_tz = get_local_timezone(tz_name)
        start_str = event['start'].get('dateTime', event['start'].get('date'))
        start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
        local_start = start_dt.astimezone(local_tz)
        time_str = local_start.strftime('%d.%m.%Y, %H:%M')
        title = event.get('summary', 'Без названия')
        link = event.get('htmlLink', '')
        user = _storage.get_user(user_id)
        city = user.get('city') if user else None
        country = user.get('country') if user else None
        weather = get_weather_detailed(city, country) if city else ""
        msg = (
            f"⏰ Напоминание!\n\n"
            f"Встреча: \"{title}\"\n"
            f"Дата и время: {time_str} ({tz_name})\n"
            f"г. {city or '—'}\n"
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть в календаре", url=link)]]) if link else None
        if weather:
            msg += f"\n{weather}"
        await _bot.send_message(chat_id=user_id, text=msg, reply_markup=keyboard)
    except Exception as e:
        print(f"Ошибка отправки уведомления: {e}")

async def _check_completed():
    now = datetime.now(dt_timezone.utc)
    users = _storage.get_all_users_with_credentials()
    for user in users:
        user_id = user['user_id']
        creds_json = user['credentials_json']
        if not creds_json:
            continue
        try:
            creds = Credentials.from_authorized_user_info(json.loads(creds_json))
            service = build('calendar', 'v3', credentials=creds)
            calendars = list_calendars(service)
            for cal in calendars:
                events = list_upcoming_events(service, calendar_id=cal['id'],
                                              time_min=(now - timedelta(hours=24)).isoformat(),
                                              time_max=now.isoformat())
                for event in events:
                    end_str = event['end'].get('dateTime', event['end'].get('date'))
                    end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
                    if end_dt < now:
                        title = event.get('summary', 'Без названия')
                        link = event.get('htmlLink', '')
                        _storage.add_history(user_id, event['id'], end_dt.isoformat(), title, link)
        except Exception as e:
            print(f"Ошибка истории user {user_id}: {e}")