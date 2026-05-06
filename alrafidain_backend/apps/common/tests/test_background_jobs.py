from django.conf import settings
from django.test import TestCase

from apps.common.job_utils import (
    create_background_job,
    mark_job_completed,
    mark_job_failed,
    mark_job_running,
)
from apps.common.models import BackgroundJobStatus


class CeleryTestSettingsTests(TestCase):
    def test_celery_runs_eagerly_in_tests(self):
        self.assertTrue(settings.CELERY_TASK_ALWAYS_EAGER)
        self.assertTrue(settings.CELERY_TASK_EAGER_PROPAGATES)


class BackgroundJobUtilsTests(TestCase):
    def test_transition_lifecycle(self):
        job = create_background_job(task_name="common.debug")
        self.assertEqual(job.status, BackgroundJobStatus.QUEUED)

        mark_job_running(job.id, celery_task_id="task-1")
        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJobStatus.RUNNING)
        self.assertEqual(job.celery_task_id, "task-1")
        self.assertIsNotNone(job.started_at)

        mark_job_completed(job.id)
        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJobStatus.COMPLETED)
        self.assertIsNotNone(job.finished_at)

    def test_mark_failed_stores_error(self):
        job = create_background_job(task_name="common.fail")
        mark_job_failed(job.id, RuntimeError("boom"))
        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJobStatus.FAILED)
        self.assertIn("boom", job.error_message)

    def test_missing_job_id_is_ignored(self):
        self.assertIsNone(mark_job_running(None))
        self.assertIsNone(mark_job_completed(None))
        self.assertIsNone(mark_job_failed(None, "x"))
