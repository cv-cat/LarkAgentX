import os
import sqlite3

ROOT = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(ROOT, 'GEOIP.db')

WEATHER_CODE = [
    {
      "code": 0,
      "wea": "晴"
    },
    {
      "code": 1,
      "wea": "多云"
    },
    {
      "code": 2,
      "wea": "阴"
    },
    {
      "code": 3,
      "wea": "阵雨"
    },
    {
      "code": 4,
      "wea": "雷阵雨"
    },
    {
      "code": 5,
      "wea": "雷阵雨并伴有冰雹"
    },
    {
      "code": 6,
      "wea": "雨夹雪"
    },
    {
      "code": 7,
      "wea": "小雨"
    },
    {
      "code": 8,
      "wea": "中雨"
    },
    {
      "code": 9,
      "wea": "大雨"
    },
    {
      "code": 10,
      "wea": "暴雨"
    },
    {
      "code": 11,
      "wea": "大暴雨"
    },
    {
      "code": 12,
      "wea": "特大暴雨"
    },
    {
      "code": 13,
      "wea": "阵雪"
    },
    {
      "code": 14,
      "wea": "小雪"
    },
    {
      "code": 15,
      "wea": "中雪"
    },
    {
      "code": 16,
      "wea": "大雪"
    },
    {
      "code": 17,
      "wea": "暴雪"
    },
    {
      "code": 18,
      "wea": "雾"
    },
    {
      "code": 19,
      "wea": "冻雨"
    },
    {
      "code": 20,
      "wea": "沙尘暴"
    },
    {
      "code": 21,
      "wea": "小雨-中雨"
    },
    {
      "code": 22,
      "wea": "中雨-大雨"
    },
    {
      "code": 23,
      "wea": "大雨-暴雨"
    },
    {
      "code": 24,
      "wea": "暴雨-大暴雨"
    },
    {
      "code": 25,
      "wea": "大暴雨-特大暴雨"
    },
    {
      "code": 26,
      "wea": "小雪-中雪"
    },
    {
      "code": 27,
      "wea": "中雪-大雪"
    },
    {
      "code": 28,
      "wea": "大雪-暴雪"
    },
    {
      "code": 29,
      "wea": "浮沉"
    },
    {
      "code": 30,
      "wea": "扬沙"
    },
    {
      "code": 31,
      "wea": "强沙尘暴"
    },
    {
      "code": 32,
      "wea": "飑"
    },
    {
      "code": 33,
      "wea": "龙卷风"
    },
    {
      "code": 34,
      "wea": "若高吹雪"
    },
    {
      "code": 35,
      "wea": "轻雾"
    },
    {
      "code": 53,
      "wea": "霾"
    },
    {
      "code": 99,
      "wea": "未知"
    }
  ]

def get_weather_code(code):
    for item in WEATHER_CODE:
        if item['code'] == int(code):
            return item['wea']
    return '未知'

def select_city_code(city):
    city = city.replace('市','')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    result = cursor.execute("SELECT city_num FROM citys WHERE name like ?", (f'{city}',))
    city_num = result.fetchone()
    if city_num:
        return city_num[0]
    else:
        return None