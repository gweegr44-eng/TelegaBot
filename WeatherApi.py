import requests
from Config import OWM_API_KEY

def get_weather_detailed(city: str, country: str = None) -> str:
    if not OWM_API_KEY:
        return "❌ Ключ погоды не настроен."
    q = f"{city}"
    if country:
        q += f",{country}"
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {'q': q, 'appid': OWM_API_KEY, 'units': 'metric', 'lang': 'ru'}
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
    except Exception as e:
        return f"❌ Ошибка соединения: {e}"
    if data.get('cod') != 200:
        return f"❌ Город не найден."
    city_name = data['name']
    temp = data['main']['temp']
    feels_like = data['main']['feels_like']
    desc = data['weather'][0]['description'].capitalize()
    humidity = data['main']['humidity']
    wind_speed = data['wind']['speed']
    pressure = data['main']['pressure']
    visibility = data.get('visibility', '—')
    return (
        f"🌤 Погода в {city_name}:\n"
        f"• Температура: {temp}°C (ощущается {feels_like}°C)\n"
        f"• {desc}\n"
        f"• Влажность: {humidity}%\n"
        f"• Ветер: {wind_speed} м/с\n"
        f"• Давление: {pressure} гПа\n"
        f"• Видимость: {visibility} м"
    )