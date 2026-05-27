"""
Management command: seed_all

Runs all seed commands in order:
    1. seed_symptoms
    2. seed_lab_order_tests
    3. seed_demo_users
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run all seed commands: seed_symptoms, seed_lab_order_tests, seed_demo_users."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("=== seed_all: starting ==="))

        self.stdout.write(self.style.MIGRATE_LABEL("--- seed_symptoms ---"))
        call_command("seed_symptoms", stdout=self.stdout, stderr=self.stderr)

        self.stdout.write(self.style.MIGRATE_LABEL("--- seed_lab_order_tests ---"))
        call_command("seed_lab_order_tests", stdout=self.stdout, stderr=self.stderr)

        self.stdout.write(self.style.MIGRATE_LABEL("--- seed_demo_users ---"))
        call_command("seed_demo_users", stdout=self.stdout, stderr=self.stderr)

        self.stdout.write(self.style.SUCCESS("=== seed_all: complete ==="))
