"""
management/commands/run_pipeline.py

Run the full job pipeline for a given Search directly from the shell,
bypassing Celery beat. Useful for local development and testing.

Usage
-----
    # Run full pipeline (scan → score → apply) for search 1
    python manage.py run_pipeline --search-id 1

    # Run only scan + score, skip apply
    python manage.py run_pipeline --search-id 1 --skip-apply

    # Run only the apply stage using already-scored candidates in the DB
    python manage.py run_pipeline --search-id 1 --apply-only

Examples
--------
    # Dev: test the full pipeline locally with browser-use running in-process
    # (requires USE_LAMBDA=False in .env and browser-use + playwright installed)
    python manage.py run_pipeline --search-id 1

    # Prod: trigger a manual run without waiting for celery beat
    python manage.py run_pipeline --search-id 1
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from jobs.models import RunLog, Search

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run the job application pipeline for a given Search.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--search-id',
            type=int,
            required=True,
            help='PK of the Search to run.',
        )
        parser.add_argument(
            '--skip-apply',
            action='store_true',
            default=False,
            help='Run scan + score only. Do not apply to any jobs.',
        )
        parser.add_argument(
            '--apply-only',
            action='store_true',
            default=False,
            help=(
                'Skip scan + score. Apply to candidates already scored in a '
                'previous run that are still in pending status.'
            ),
        )

    def handle(self, *args, **options):
        search_id = options['search_id']
        skip_apply = options['skip_apply']
        apply_only = options['apply_only']

        if skip_apply and apply_only:
            raise CommandError('--skip-apply and --apply-only are mutually exclusive.')

        # Load and validate search.
        try:
            search = Search.objects.select_related('agent__user').get(pk=search_id)
        except Search.DoesNotExist:
            raise CommandError(f'Search with id={search_id} does not exist.')

        use_lambda = getattr(settings, 'USE_LAMBDA', True)

        self.stdout.write(
            self.style.NOTICE(
                f'\n→ Running pipeline for search_id={search_id} '
                f'("{search.label or "Search"}" — {search.agent.user.username})\n'
                f'  USE_LAMBDA={use_lambda}\n'
                f'  skip_apply={skip_apply} | apply_only={apply_only}\n'
            )
        )

        if apply_only:
            self._run_apply_only(search)
        else:
            self._run_full(search, skip_apply)

    # ------------------------------------------------------------------
    # Full pipeline: scan → score → apply
    # ------------------------------------------------------------------

    def _run_full(self, search: Search, skip_apply: bool) -> None:
        from pipeline.tasks.scan_jobs import scan_jobs
        from pipeline.tasks.score_jobs import score_jobs
        from pipeline.tasks.apply_job import apply_jobs

        log = RunLog.objects.create(search=search, status='running')
        self.stdout.write(f'  RunLog id={log.pk} created.\n')

        # Stage 1: scan
        self.stdout.write(self.style.NOTICE('→ Stage 1: scan_jobs'))
        unseen_jobs = scan_jobs(search.pk)
        log.jobs_fetched = len(unseen_jobs)
        log.save(update_fields=['jobs_fetched'])
        self.stdout.write(f'  Fetched {len(unseen_jobs)} unseen jobs.\n')

        if not unseen_jobs:
            log.status = 'completed'
            log.save(update_fields=['status'])
            self.stdout.write(self.style.SUCCESS('  No new jobs. Pipeline complete.'))
            return

        # Stage 2: score
        self.stdout.write(self.style.NOTICE('→ Stage 2: score_jobs'))
        scored_jobs = score_jobs(search.pk, unseen_jobs)

        score_failures = [j for j in scored_jobs if j.get('_score_failed')]
        candidates = [j for j in scored_jobs if not j.get('_score_failed')]

        log.jobs_scored = len(candidates)
        log.jobs_failed = len(score_failures)
        log.save(update_fields=['jobs_scored', 'jobs_failed'])

        self.stdout.write(
            f'  Scored {len(candidates)} candidates '
            f'({len(score_failures)} scoring failures).\n'
        )

        for job in candidates:
            self.stdout.write(
                f'    [{job["llm_score"]}/10] {job["company"]} — {job["title"]}\n'
                f'             {job["job_url"]}\n'
            )

        if not candidates:
            log.status = 'completed' if not score_failures else 'partial'
            log.save(update_fields=['status'])
            self.stdout.write(self.style.WARNING('  No candidates above threshold.'))
            return

        if skip_apply:
            log.status = 'completed'
            log.save(update_fields=['status'])
            self.stdout.write(self.style.WARNING('  --skip-apply set. Stopping before apply stage.'))
            return

        # Stage 3: apply
        self.stdout.write(self.style.NOTICE('→ Stage 3: apply_jobs'))
        # TODO: insert cover letter personalisation here before apply_jobs
        apply_jobs(search.pk, candidates, log)

        log.refresh_from_db()

        total_failures = log.jobs_failed
        total_jobs = log.jobs_fetched

        if log.status not in ('failed', 'partial'):
            if total_failures == total_jobs:
                log.status = 'failed'
            elif total_failures > 0:
                log.status = 'partial'
            else:
                log.status = 'completed'
            log.save(update_fields=['status'])

        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ Pipeline complete — '
                f'fetched={log.jobs_fetched} '
                f'scored={log.jobs_scored} '
                f'applied={log.jobs_applied} '
                f'failed={log.jobs_failed} '
                f'status={log.status}\n'
            )
        )

    # ------------------------------------------------------------------
    # Apply-only: re-apply pending candidates from a previous run
    # ------------------------------------------------------------------

    def _run_apply_only(self, search: Search) -> None:
        from jobs.models import Application
        from pipeline.tasks.apply_job import apply_jobs

        pending = Application.objects.filter(
            search=search,
            status='pending',
        ).select_related('resume')

        if not pending.exists():
            self.stdout.write(self.style.WARNING(
                f'  No pending applications found for search_id={search.pk}.'
            ))
            return

        self.stdout.write(f'  Found {pending.count()} pending applications.\n')

        # Re-build job dicts from Application records for apply_jobs.
        candidates = []
        for app in pending:
            candidates.append({
                'job_id':          app.job_id,
                'job_url':         app.job_url,
                'apply_link':      app.job_url,
                'company':         app.company,
                'title':           app.role_title,
                'location':        app.location,
                'remote_type':     app.remote_type,
                'salary_range':    app.salary_range,
                'description':     app.job_description or '',
                'llm_score':       app.llm_score,
                'llm_score_reason': app.llm_score_reason,
                'cover_letter':    app.cover_letter_used or '',
            })

            # Reset to pending so apply_jobs doesn't skip on get_or_create.
            app.delete()

        log = RunLog.objects.create(search=search, status='running')
        log.jobs_fetched = len(candidates)
        log.jobs_scored = len(candidates)
        log.save(update_fields=['jobs_fetched', 'jobs_scored'])

        self.stdout.write(self.style.NOTICE('→ apply_jobs'))
        apply_jobs(search.pk, candidates, log)

        log.refresh_from_db()
        log.status = 'completed' if log.jobs_failed == 0 else 'partial'
        log.save(update_fields=['status'])

        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ Apply-only complete — '
                f'applied={log.jobs_applied} '
                f'failed={log.jobs_failed} '
                f'status={log.status}\n'
            )
        )