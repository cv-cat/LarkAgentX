from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from app.core.mcp_server import send_message
from app.db.session import get_db_session, close_db_session
from app.db.models import Schedule
import importlib
from apscheduler.schedulers.background import BackgroundScheduler

from apscheduler.triggers.cron import CronTrigger

# 重写Cron定时
class SecondCronTrigger(CronTrigger):
    @classmethod
    def from_crontab(cls, expr, timezone=None):
        values = expr.split()
        if len(values) != 6:
            raise ValueError('Wrong number of fields; got {}, expected 6'.format(len(values)))

        return cls(second=values[0], minute=values[1], hour=values[2], day=values[3], month=values[4],
                   day_of_week=values[5], timezone=timezone)

class YearCronTrigger(CronTrigger):
    @classmethod
    def from_crontab(cls, expr, timezone=None):
        values = expr.split()
        if len(values) != 7:
            raise ValueError('Wrong number of fields; got {}, expected 7'.format(len(values)))

        return cls(second=values[0], minute=values[1], hour=values[2], day=values[3], month=values[4],
                   day_of_week=values[5],year=values[6], timezone=timezone)

class ScheduleService:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler._logger = logger
        self.db = get_db_session()
        self.tasks = self.db.query(Schedule).filter(Schedule.active == True).all()
        for task in self.tasks:
            self.add_schedule(task)
        self.scheduler.add_job(func=self.new_task_watcher, trigger='interval', seconds=5, id=f'-1')
        self.scheduler.start()

    def new_task_watcher(self):
        ids = [t.id for t in self.tasks]
        news = (self.db.query(Schedule)
                .filter(Schedule.active == True)
                .filter(Schedule.id.notin_(ids))
                .all()
                )
        for new in news:
            self.add_schedule(new)


    def add_schedule(self, task: Schedule):
        cron = task.cron
        def run_task():
            module = importlib.import_module(task.module_name)
            func = getattr(module, task.function_name)
            args = task.arguments
            if callable(func):
                result = func(*args)
                send_message(task.created_by, result)
        if len(cron.split(' ')) == 6:
            cron = SecondCronTrigger.from_crontab(cron)
        elif len(cron.split(' ')) == 5:
            cron = CronTrigger.from_crontab(cron)
        elif len(cron.split(' ')) == 7:
            cron = YearCronTrigger.from_crontab(cron)
        self.scheduler.add_job(run_task, cron, id=f'{task.id}')
        logger.info(f'添加定时任务成功, {task}')

    def close(self):
        close_db_session(self.db)
        self.scheduler.shutdown()


