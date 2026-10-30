from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

from backend.automation_agent.notification_tasks import send_notification


IST = ZoneInfo("Asia/Kolkata")

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "data" / "scheduler.sqlite"


class MeetingScheduler:

    def __init__(self):
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

        jobstores = {
            "default": SQLAlchemyJobStore(
                url=f"sqlite:///{DATABASE_PATH.as_posix()}"
            )
        }

        executors = {
            "default": ThreadPoolExecutor(5)
        }

        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            timezone=IST
        )

        self.scheduler.start()

    def schedule_meeting(self, meeting):

        meeting_time = datetime.fromisoformat(
            meeting["datetime"]
        ).replace(tzinfo=IST)

        participants = meeting["participants"]

        for recipient in participants:

            for notification_type, offset in [
                ("reminder_24h", timedelta(hours=24)),
                ("reminder_30m", timedelta(minutes=30))
            ]:

                run_time = meeting_time - offset

                if run_time <= datetime.now(IST):
                    print(
                        f"[SKIPPED] {notification_type} for "
                        f"{recipient['name']} - scheduled time has passed."
                    )
                    continue

                self.scheduler.add_job(
                    send_notification,
                    trigger="date",
                    run_date=run_time,
                    args=[
                        notification_type,
                        meeting,
                        recipient
                    ],
                    id=f"{uuid4().hex}",
                    replace_existing=False,
                    misfire_grace_time=3600
                )

                print(
                    f"[SCHEDULED] {notification_type} for "
                    f"{recipient['name']} at {run_time}"
                )

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)