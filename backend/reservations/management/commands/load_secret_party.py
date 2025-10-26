from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
import logging
import os
import sys

import reservations.config as roombaht_config

class Command(BaseCommand):
    help = 'Load guests from a CSV (same format as admin guest upload) and process through the ingestion pipeline'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            dest='file',
            help='Path to CSV file to load'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview what would be done without making changes',
        )

    def setup_logging(self):
        logger = logging.getLogger()
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        # Respect Django verbosity if available; default INFO
        # (Django's BaseCommand sets verbosity on self.verbosity)
        if getattr(self, 'verbosity', None) is not None:
            if self.verbosity == 0:
                logger.setLevel(logging.WARNING)
            elif self.verbosity == 1:
                logger.setLevel(logging.INFO)
            else:
                logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(roombaht_config.LOGLEVEL)

    def handle(self, *args, **options):
        self.verbosity = options.get('verbosity', 1)
        self.setup_logging()
        logger = logging.getLogger(__name__)

        file_path = options['file']
        dry_run = options['dry_run']

        if not os.path.exists(file_path):
            raise CommandError(f"CSV file not found: {file_path}")

        # Use GuestIngestionService for complete processing pipeline
        from reservations.services.guest_ingestion_service import GuestIngestionService

        ingestion_service = GuestIngestionService()

        # Configure CSV source processing
        config = {'file_path': file_path}

        # Dry-run only previews; does not run DB processing
        if dry_run:
            # For dry-run, we need to peek at the CSV data without full processing
            from reservations.helpers import ingest_csv
            from reservations.services.guest_validation_service import GuestValidationService
            import re

            # Ingest and normalize CSV data (same as admin.py)
            guest_fields, original_guests = ingest_csv(file_path)

            if 'ticket_code' not in guest_fields or 'product' not in guest_fields:
                raise CommandError("CSV missing required headers: ticket_code and product")

            # Normalize product strings (same as admin.py)
            for o_guest in original_guests:
                raw_product = o_guest.get('product', '')
                o_guest['product'] = re.sub(r'[\d\.]+ RS24 ', '', raw_product)

            # Apply validation to see what would be processed
            validation_service = GuestValidationService()
            new_guests = validation_service.filter_valid_guests(original_guests)

            self.stdout.write(self.style.WARNING("DRY RUN - No database changes will be made"))
            self.stdout.write(f"Input rows: {len(original_guests)}")
            self.stdout.write(f"Valid new rows: {len(new_guests)}")
            if len(new_guests) > 0:
                self.stdout.write("Sample valid tickets:")
                for r in new_guests[:10]:
                    self.stdout.write(f"  {r.get('ticket_code')} - {r.get('first_name', '')} {r.get('last_name', '')} ({r.get('email', '')})")
            return

        # Process through the complete ingestion pipeline with transaction safety
        try:
            with transaction.atomic():
                result = ingestion_service.ingest_from_external_source('csv', config)

                if not result.get('success', True):
                    raise CommandError(f"Processing reported failure: {result}")

                # Output room counts information (matches original behavior)
                room_counts_output = result.get('room_counts_output', [])
                for line in room_counts_output:
                    self.stdout.write(line)

                # Output validation statistics
                validation_stats = result.get('validation_stats', {})
                self.stdout.write(f"Processed {validation_stats.get('valid_guests', 0)} valid guests "
                                f"out of {validation_stats.get('total_input_guests', 0)} total records")

                self.stdout.write(self.style.SUCCESS("Guest import completed"))

        except Exception as e:
            raise CommandError(f"Processing failed and was rolled back: {e}")
