from apscheduler.jobstores.base import JobLookupError
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
        self.scheduler.add_job(func=self.task_watcher, trigger='interval', seconds=5, id=f'-1')
        self.scheduler.start()

    def task_watcher(self):
        ids = [t.id for t in self.tasks]
        news = (self.db.query(Schedule)
                .filter(Schedule.active == True)
                .filter(Schedule.id.notin_(ids))
                .all()
                )
        if len(news) > 0:
            logger.info(f'新增定时任务, {news}')
        removed = (self.db.query(Schedule).filter(Schedule.active == False).all())
        for removed_task in removed:
            if removed_task.id in ids:
                self.tasks = [t for t in self.tasks if t.id!= removed_task.id]
                ids = [t.id for t in self.tasks]
                self.remove_schedule(removed_task.id)
        for new in news:
            self.add_schedule(new)
            self.tasks.append(new)


    def add_schedule(self, task: Schedule):
        try:
            cron = task.cron

            def run_task(_task):
                logger.info(f'开始执行定时任务, {_task}')
                module = importlib.import_module(_task.module_name)
                func = getattr(module, _task.function_name)
                args = _task.arguments
                if callable(func):
                    result = func(*args)
                    send_message(user_id=_task.created_by, content=result)
                    logger.info(f'定时任务执行成功, {_task}')

            if len(cron.split(' ')) == 6:
                cron = SecondCronTrigger.from_crontab(cron)
            elif len(cron.split(' ')) == 5:
                cron = CronTrigger.from_crontab(cron)
            elif len(cron.split(' ')) == 7:
                cron = YearCronTrigger.from_crontab(cron)
            self.scheduler.add_job(run_task, args=[task], trigger=cron, id=f'{task.id}')
            logger.info(f'添加定时任务成功, {task}')
        except Exception as e:
            logger.error(f'添加定时任务失败, {task}, {e}')

    def remove_schedule(self, task_id: int):
        try:
            self.scheduler.remove_job(f'{task_id}')
        except JobLookupError:
            pass
        logger.info(f'删除定时任务成功, {task_id}')

    def close(self):
        close_db_session(self.db)
        self.scheduler.shutdown()


