import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

broker = os.getenv("REDIS_URL", "redis://localhost:6379/0")
backend = broker

celery = Celery("wardrobe_workers", broker=broker, backend=backend, include=["workers.tasks"])
celery.conf.task_routes = {
    "tasks.process_image": {"queue": "images"},
    "tasks.analyze_image": {"queue": "images"},
}
