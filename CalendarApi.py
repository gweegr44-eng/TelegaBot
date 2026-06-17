from googleapiclient.discovery import build
from datetime import datetime, timedelta, timezone as dt_timezone

def build_service(credentials):
    return build('calendar', 'v3', credentials=credentials)

def list_upcoming_events(service, calendar_id='primary', time_min=None, time_max=None, max_results=50):
    if time_min is None:
        time_min = datetime.utcnow().isoformat() + 'Z'
    if time_max is None:
        time_max = (datetime.utcnow() + timedelta(hours=2)).isoformat() + 'Z'
    events_result = service.events().list(
        calendarId=calendar_id, timeMin=time_min,
        timeMax=time_max, singleEvents=True,
        orderBy='startTime'
    ).execute()
    return events_result.get('items', [])

def list_calendars(service):
    calendars = service.calendarList().list().execute()
    return calendars.get('items', [])

def get_primary_timezone(service):
    try:
        cal = service.calendarList().get(calendarId='primary').execute()
        return cal.get('timeZone')
    except:
        return None

def list_events_for_date(service, calendar_id='primary', date_str=None, timezone_str='Europe/Moscow'):
    if 'Moscow' in timezone_str:
        offset_hours = 3
    elif 'Yekaterinburg' in timezone_str:
        offset_hours = 5
    else:
        offset_hours = 3
    tz = dt_timezone(timedelta(hours=offset_hours))
    if date_str is None:
        today = datetime.now(tz).date()
    else:
        today = datetime.strptime(date_str, '%Y-%m-%d').date()
    start_of_day = datetime.combine(today, datetime.min.time(), tzinfo=tz)
    end_of_day = start_of_day + timedelta(days=1)
    time_min = start_of_day.isoformat()
    time_max = end_of_day.isoformat()
    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    return events_result.get('items', [])