import json
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from Config import TZ
from Storage import Storage
from CalendarApi import list_upcoming_events
import asyncio

notified_events = {}

def check_and_notify(bot, storage: Storage):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_async_check(bot, storage))
    finally:
        loop.close()

async def _async_check(bot, storage: Storage):
    now_utc = datetime.utcnow()
    users = storage.get_all_users_with_credentials()
    for user in users:
        user_id = user['user_id']
        reminder_minutes = user.get('reminder_minutes', 30)
        calendar_id = user.get('calendar_id', 'primary')
        credentials_json = user['credentials_json']
        if not credentials_json:
            continue
        try:
            creds = Credentials.from_authorized_user_info(json.loads(credentials_json))
            service = build('calendar', 'v3', credentials=creds)
            time_min = now_utc.isoformat() + 'Z'
            time_max = (now_utc + timedelta(hours=2)).isoformat() + 'Z'
            events = list_upcoming_events(service, calendar_id=calendar_id,
                                          time_min=time_min, time_max=time_max)
            for event in events:
                event_id = event['id']
                start_str = event['start'].get('dateTime', event['start'].get('date'))
                end_str = event['end'].get('dateTime', event['end'].get('date'))
                start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
                delta_min = (start_dt - now_utc.replace(tzinfo=timezone.utc)).total_seconds() / 60
                if 0 < delta_min <= reminder_minutes:
                    if user_id not in notified_events:
                        notified_events[user_id] = set()
                    if event_id in notified_events[user_id]:
                        continue
                    title = event.get('summary', 'Без названия')
                    link = event.get('htmlLink', '')
                    local_time = start_dt.astimezone(timezone(timedelta(hours=3)))
                    time_str = local_time.strftime('%d.%m.%Y, %H:%M')
                    msg = (f"⏰ Напоминание!\n\n"
                           f"Встреча: \"{title}\"\n"
                           f"Время: {time_str} (МСК)\n"
                           f"Ссылка: {link}")
                    await bot.send_message(chat_id=user_id, text=msg)
                    notified_events[user_id].add(event_id)
                if end_dt < now_utc.replace(tzinfo=timezone.utc):
                    title = event.get('summary', 'Без названия')
                    link = event.get('htmlLink', '')
                    storage.add_history(user_id, event_id, end_dt.isoformat(), title, link)
        except Exception as e:
            print(f"[Scheduler] Ошибка user_id={user_id}: {e}")

def start_scheduler(bot, storage: Storage):
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: check_and_notify(bot, storage), 'interval', minutes=5, id='calendar_check')
    scheduler.start()
    print("[Scheduler] Планировщик запущен (интервал 5 мин)")