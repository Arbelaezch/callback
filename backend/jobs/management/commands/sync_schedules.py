"""
python manage.py sync_schedules

Syncs Search.schedule_enabled → django-celery-beat PeriodicTask entries.

Run on container startup and called automatically after any schedule toggle via the API.
Each scheduled Search gets its own PeriodicTask named "run-search-<id>".
Disabling removes the task entirely so beat never sees it.
"""

import json
import logging

from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from jobs.models import Search

logger = logging.getLogger(__name__)

TASK_NAME_PREFIX = 'run-search-'
TASK_PATH = 'pipeline.tasks.daily_run.daily_run'

# Fires at 08:00 UTC daily. Change here to move all searches together.
SCHEDULE_HOUR = 8
SCHEDULE_MINUTE = 0


def _task_name(search_id):
    return f'{TASK_NAME_PREFIX}{search_id}'


def _get_or_create_crontab():
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute=str(SCHEDULE_MINUTE),
        hour=str(SCHEDULE_HOUR),
        day_of_week='*',
        day_of_month='*',
        month_of_year='*',
    )
    return schedule


def sync_schedules():
    """
    Core sync logic. Called by the management command and by SearchScheduleView
    after a schedule toggle so both paths stay in sync.
    """
    crontab = _get_or_create_crontab()

    searches = Search.objects.all().only('id', 'schedule_enabled')
    enabled_ids = set()
    disabled_ids = set()

    for search in searches:
        if search.schedule_enabled:
            enabled_ids.add(search.id)
        else:
            disabled_ids.add(search.id)

    # Enable: create or re-enable PeriodicTask
    for search_id in enabled_ids:
        name = _task_name(search_id)
        task, created = PeriodicTask.objects.update_or_create(
            name=name,
            defaults={
                'task': TASK_PATH,
                'crontab': crontab,
                'kwargs': json.dumps({'search_id': search_id}),
                'enabled': True,
            },
        )
        action = 'created' if created else 'updated'
        logger.info('[sync_schedules] %s PeriodicTask for search id=%s', action, search_id)

    # Disable: delete PeriodicTask entirely so beat never queues it
    names_to_delete = [_task_name(sid) for sid in disabled_ids]
    deleted_count, _ = PeriodicTask.objects.filter(name__in=names_to_delete).delete()
    if deleted_count:
        logger.info('[sync_schedules] deleted %d PeriodicTask(s) for disabled searches', deleted_count)

    return {'enabled': len(enabled_ids), 'disabled': len(disabled_ids)}


class Command(BaseCommand):
    help = 'Sync Search.schedule_enabled to django-celery-beat PeriodicTask entries.'

    def handle(self, *args, **options):
        result = sync_schedules()
        self.stdout.write(
            self.style.SUCCESS(
                f"sync_schedules: {result['enabled']} enabled, {result['disabled']} disabled/removed"
            )
        )