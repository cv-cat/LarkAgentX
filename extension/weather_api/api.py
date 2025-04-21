from datetime import datetime

import requests

from .db import select_city_code, get_weather_code


def get_city_geocode(city):
    """
    Get the geocode of a city in a province.
    """
    return select_city_code(city)

def get_city_weather(city):
    """
    Get the weather of a city in a province.
    """
    URL = f'https://weatherapi.market.xiaomi.com/wtr-v3/weather/all'
    city_code = select_city_code(city)

    if city_code:
        result = f'地区:{city}的天气情况\n'
        date = datetime.today().strftime('%Y%m%d')
        params = {
            'latitude': 0,
            'longitude': 0,
            'locationKey': f'weathercn:{city_code}',
            'appKey': f'weather{date}',
            'sign': 'zUFJoAR2ZVrDy1vF3D07',
            'isGlobal': 'false',
            'locale': 'zh_CN',
            'days': '1'
        }
        response = requests.get(URL, params=params)
        data = response.json()
        current = data['current']
        temperature = current['temperature']
        result += f'温度： {temperature["value"]}{temperature["unit"]}\n'
        weather_code = current['weather']
        weather = get_weather_code(weather_code)
        result += f'当前天气: {weather}\n'
        pressure = current['pressure']
        result += f'气压: {pressure["value"]}{pressure["unit"]}\n'
        humidity = current['humidity']
        result += f'湿度: {humidity["value"]}{humidity["unit"]}\n'
        visibility = current['visibility']
        if len(visibility['value']) > 0:
            result += f'能见度: {visibility["value"]}{visibility["unit"]}\n'
        wind = current['wind']
        result += f'风向: {wind["direction"]["value"]}{wind["direction"]["unit"]}\n'
        result += f'风力: {wind["speed"]["value"]}{wind["speed"]["unit"]}\n'
        forecastDaily = data['forecastDaily']
        aqi = forecastDaily['aqi']
        if aqi['status'] == 0:
            value = aqi['value']
            result += f'今天空气质量指数: {value[0]}\n'
        precipitationProbability = forecastDaily['precipitationProbability']
        if precipitationProbability['status'] == '0':
            value = precipitationProbability['value']
            result += f'\n今天降水概率: {value[0]}\n'
            result += f'未来几天降水概率: {value[1:]}\n'
        sunRiseSet = forecastDaily['sunRiseSet']
        if sunRiseSet['status'] == 0:
            value = sunRiseSet["value"]
            result += f'今日日出时间: {value[0]["from"]}\n'
            result += f'今日日落时间: {value[0]["to"]}\n'
        temperature = forecastDaily['temperature']
        if temperature['status'] ==0:
            value = temperature['value']
            result += f'今日气温：: {min(value[0]["from"], value[0]["to"])}-{max(value[0]["to"], value[1]["from"])}{temperature["unit"]}\n'
        return result

if __name__ == '__main__':
    print(get_city_weather('北京'))