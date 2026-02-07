import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

broker = os.getenv("REDIS_URL", "redis://localhost:6379/0")
backend = broker

celery = Celery("wardrobe_workers", broker=broker, backend=backend, include=["workers.tasks"])
celery.conf.task_routes = {
    "tasks.process_image": {"queue": "images"},
    "tasks.analyze_image": {"queue": "images"},
    "tasks.analyze_outfit_photo": {"queue": "images"},
    "tasks.analyze_outfit_match_job": {"queue": "images"},
    "tasks.refresh_user_quality": {"queue": "quality"},
    "tasks.refresh_all_quality_scores": {"queue": "quality"},
    "tasks.cleanup_quality_history": {"queue": "quality"},
    "tasks.cleanup_vote_sessions": {"queue": "quality"},
}

# Beat schedule for periodic tasks
celery.conf.beat_schedule = {
    "refresh-quality-scores-weekly": {
        "task": "tasks.refresh_all_quality_scores",
        "schedule": crontab(hour=3, minute=0, day_of_week=0),  # Sunday 3 AM
    },
    "cleanup-quality-history-monthly": {
        "task": "tasks.cleanup_quality_history",
        "schedule": crontab(hour=4, minute=0, day_of_month=1),  # 1st of month 4 AM
    },
    "cleanup-vote-sessions-daily": {
        "task": "tasks.cleanup_vote_sessions",
        "schedule": crontab(hour=2, minute=30),  # Daily 2:30 AM
    },
}
