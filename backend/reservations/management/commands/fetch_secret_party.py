from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
import logging

from reservations.config import SP_API_KEY
from reservations.secret_party import SecretPartyClient, SecretPartyAPIError, SecretPartyAuthError
from reservations.services.guest_ingestion_service import GuestIngestionService
from reservations.ingest_models import SecretPartyGuestIngest


class Command(BaseCommand):
    help = 'Fetch guest data from Secret Party API and process through the ingestion pipeline'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview what would be done without making any changes',
        )
        parser.add_argument(
            '--no-cache',
            action='store_true',
            dest='no_cache',
            help='Bypass cached ticket export and force fresh fetch from Secret Party API',
        )

    def setup_logging(self):
        logger = logging.getLogger()
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        # Set log level based on verbosity
        if self.verbosity == 0:
            logger.setLevel(logging.WARNING)
        elif self.verbosity == 1:
            logger.setLevel(logging.INFO)
        else:
            logger.setLevel(logging.DEBUG)

    def validate_config(self):
        """Validate required configuration."""
        if not SP_API_KEY:
            raise CommandError(
                "Secret Party API key not found. Please set ROOMBAHT_SP_API_KEY environment variable."
            )

    def fetch_tickets(self, client, options):
        """
        Fetch tickets from Secret Party API based on command options.

        Args:
            client: SecretPartyClient instance
            options: Command options dictionary

        Returns:
            List of ticket dictionaries
        """
        try:
            # Fetch all active and transferred tickets (default)
            self.stdout.write("Fetching all active and transferred tickets...")
            tickets = client.get_all_active_and_transferred_tickets(
                order=options.get('order'),
                reverse=options.get('reverse'),
                force=options.get('no_cache', False)
            )

            return tickets

        except SecretPartyAuthError as e:
            raise CommandError(f"Secret Party authentication failed: {e}")
        except SecretPartyAPIError as e:
            raise CommandError(f"Secret Party API error: {e}")

    def process_tickets(self, tickets, dry_run=False):
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))
            self.stdout.write("Would process tickets from Secret Party API...")
            if tickets:
                self.stdout.write(f"Sample tickets (showing first 3 of {len(tickets)}):")
                for i, ticket in enumerate(tickets[:3]):
                    self.stdout.write(f"  {i+1}. {ticket.get('first_name', '')} {ticket.get('last_name', '')} ({ticket.get('email', '')})")
                if len(tickets) > 3:
                    self.stdout.write(f"  ... and {len(tickets) - 3} more")
            return {"dry_run": True, "ticket_count": len(tickets) if tickets else 0}

        # Process through ingestion service
        try:
            ingestion_service = GuestIngestionService()

            results = ingestion_service.ingest_from_external_source('secretparty')
            return results
        except Exception as e:
            raise CommandError(f"Guest processing failed: {e}")

    def handle(self, *args, **options):
        """Main command handler."""
        self.verbosity = options.get('verbosity', 1)
        self.options = options  # Store options for use in other methods
        self.setup_logging()

        # Validate configuration
        self.validate_config()

        self.stdout.write("Starting Secret Party guest ingestion...")

        # Process tickets
        if options['dry_run']:
            # For dry run, we still need to fetch tickets to show what would be processed
            try:
                client = SecretPartyClient(SP_API_KEY)
                # tickets are returned orderd by date desc
                tickets = self.fetch_tickets(client, options)
                tickets.reverse()
                results = self.process_tickets(tickets, dry_run=True)
                self.stdout.write(
                    self.style.SUCCESS(f"Dry run complete. Would process {results.get('ticket_count', 0)} tickets.")
                )
            except Exception as e:
                raise CommandError(f"Dry run failed: {e}")
        else:
            # Use database transaction for safety
            try:
                with transaction.atomic():
                    results = self.process_tickets(None, dry_run=False)

                    # Report results
                    if results.get('success', False):
                        self.stdout.write(self.style.SUCCESS("Secret Party ingestion completed successfully!"))

                        # Display summary information
                        if 'total_processed' in results:
                            self.stdout.write(f"Total guests processed: {results['total_processed']}")
                        if 'source_metadata' in results:
                            metadata = results['source_metadata']
                            self.stdout.write(f"Source records: {metadata.get('total_records', 'unknown')}")
                            self.stdout.write(f"Fetch time: {metadata.get('fetch_timestamp', 'unknown')}")
                    else:
                        error_msg = results.get('error', 'Unknown error')
                        raise CommandError(f"Processing failed: {error_msg}")

            except Exception as e:
                self.stderr.write(f"Processing failed and was rolled back: {e}")
                raise CommandError(f"Secret Party ingestion failed: {e}")
