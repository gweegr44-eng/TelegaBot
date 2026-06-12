from googleapiclient.discovery import build
from datetime import datetime, timedelta

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