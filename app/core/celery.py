"""
Celery configuration for background tasks and scheduled jobs.
"""

from celery import Celery

from app.core.config import settings

# Create Celery app
celery_app = Celery(
    "trojan_trading_analytics",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.tracking_tasks"
    ]
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=600,  # 10 minutes
    task_soft_time_limit=540,  # 9 minutes soft limit
    broker_connection_retry_on_startup=True,
    result_expires=3600,  # 1 hour
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Configure scheduled tasks
celery_app.conf.beat_schedule = {
    "check-tracking-jobs": {
        "task": "app.tasks.tracking_tasks.check_and_execute_tracking_jobs",
        "schedule": 30.0,  # Check every 30 seconds
        "options": {"expires": 25.0}  # Expire if not executed within 25 seconds
    },
    "cache-cleanup": {
        "task": "app.tasks.tracking_tasks.cleanup_expired_cache",
        "schedule": 300.0,  # Clean cache every 5 minutes
        "options": {"expires": 290.0}
    }
}

# Make Celery app available for import
__all__ = ["celery_app"] 