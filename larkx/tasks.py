"""定时任务:三种写法,到点后交给创建它的那个会话的 agent。

    --in 30m / 2h / 1d       多久之后执行一次
    --at "2026-11-09 09:00"  指定时间执行一次(也可以只写 "09:00",指今天或明天的这个时间)
    --daily 09:00            每天这个时间执行

账号没在运行时到点了:启动后补跑一次;一次性任务超过 LATE_LIMIT 就作废,不发过时的提醒。
"""
import re
from datetime import datetime, timedelta

LATE_LIMIT = 3600
_DURATION = re.compile(r'^\s*(\d+)\s*([smhd]|min|分钟|小时|天)\s*$')
_HHMM = re.compile(r'^([01]?\d|2[0-3]):([0-5]\d)$')
_UNITS = {'s': 1, 'm': 60, 'min': 60, '分钟': 60, 'h': 3600, '小时': 3600, 'd': 86400, '天': 86400}


def parse_in(text: str, now: datetime = None) -> datetime:
    m = _DURATION.match(text or '')
    if not m or int(m.group(1)) <= 0:
        raise ValueError(f'看不懂「{text}」,写成 30m、2h、1d 这样')
    return (now or datetime.now()) + timedelta(seconds=int(m.group(1)) * _UNITS[m.group(2)])


def parse_hhmm(text: str) -> str:
    m = _HHMM.match((text or '').strip())
    if not m:
        raise ValueError(f'看不懂「{text}」,写成 09:00 这样')
    return f'{int(m.group(1)):02d}:{m.group(2)}'


def parse_at(text: str, now: datetime = None) -> datetime:
    now = now or datetime.now()
    text = (text or '').strip()
    if _HHMM.match(text):
        h, mi = map(int, parse_hhmm(text).split(':'))
        t = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        return t if t > now else t + timedelta(days=1)
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%m-%d %H:%M'):
        try:
            t = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt == '%m-%d %H:%M':
            t = t.replace(year=now.year)
        if t <= now:
            raise ValueError(f'{text} 已经过去了')
        return t
    raise ValueError(f'看不懂「{text}」,写成 "2026-11-09 09:00" 或 "09:00"')


def next_daily(hhmm: str, after: datetime) -> datetime:
    """after 之后第一次到 hhmm 的时间。"""
    h, mi = map(int, hhmm.split(':'))
    t = after.replace(hour=h, minute=mi, second=0, microsecond=0)
    return t if t > after else t + timedelta(days=1)


def due(task, now: datetime) -> str:
    """'run' 现在执行;'expire' 一次性任务过期太久,作废;'' 还没到。"""
    if task.run_at and now.timestamp() >= task.run_at:
        if task.kind == 'once' and now.timestamp() - task.run_at > LATE_LIMIT:
            return 'expire'
        return 'run'
    return ''


def describe(task) -> str:
    if task.kind == 'daily':
        return f'每天 {task.daily_at}'
    return datetime.fromtimestamp(task.run_at).strftime('%Y-%m-%d %H:%M')
