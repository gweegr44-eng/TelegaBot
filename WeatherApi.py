import requests
from config import OWM_API_KEY

def get_weather(city: str, country: str = None) -> str:
    if not OWM_API_KEY:
        return "❌ Ключ API погоды не настроен. Добавьте OWM_API_KEY в .env"

    q = f"{city}"
    if country:
        q += f",{country}"

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        'q': q,
        'appid': OWM_API_KEY,
        'units': 'metric',
        'lang': 'ru'
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
    except Exception as e:
        return f"❌ Ошибка соединения: {e}"

    if data.get('cod') != 200:
        return f"❌ Ошибка: {data.get('message', 'город не найден')}"

    city_name = data['name']
    temp = data['main']['temp']
    feels_like = data['main']['feels_like']
    description = data['weather'][0]['description']
    humidity = data['main']['humidity']
    wind_speed = data['wind']['speed']

    return (f"🌤 Погода в {city_name}:\n"
            f"• Температура: {temp}°C (ощущается как {feels_like}°C)\n"
            f"• {description.capitalize()}\n"
            f"• Влажность: {humidity}%\n"
            f"• Ветер: {wind_speed} м/с")