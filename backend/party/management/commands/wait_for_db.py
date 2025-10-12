import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.utils import OperationalError

class Command(BaseCommand):
    """Wait for the database to be ready"""

    def handle(self, *args, **options):
        self.stdout.write('Waiting for database...')

        while True:
            try:
                connection.cursor()
                break
            except OperationalError as e:
                if ("does not exist" in e.args[0]):
                    db_name = settings.DATABASES['default']['NAME']
                    with connection._nodb_cursor() as cursor:
                        cursor.execute(f'CREATE DATABASE "{db_name}"')
            self.stdout.write('Database unavailable, waiting 1 second...')
            time.sleep(1)

        self.stdout.write(self.style.SUCCESS('Database is ready'))
