import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from reservations.models import Guest, Room
from reservations.secret_party import SecretPartyClient
from reservations.ingest_models import SecretPartyGuestIngest
from reservations.services.room_assignment_service import RoomAssignmentService
from reservations.services.guest_management_service import GuestManagementService
from reservations.helpers import phrasing
from reservations.constants import ROOM_LIST
from reservations.management import getch
import reservations.config as roombaht_config


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fix guest with room product but no room assigned"

    def add_arguments(self, parser):
        parser.add_argument('search', help='Email or ticket ID to search for')
        parser.add_argument('--ticket', action='store_true',
                            help='Search by ticket instead of email')
        parser.add_argument('--dry-run', '-d', action='store_true',
                            help='Show changes without applying')
        parser.add_argument('--force', '-f', action='store_true',
                            help='Skip confirmation prompts')

    def handle(self, *args, **kwargs):
        search = kwargs['search']
        search_by_ticket = kwargs['ticket']
        dry_run = kwargs['dry_run']
        force = kwargs['force']

        # Step 1: Lookup guest
        guest = self._lookup_guest(search, search_by_ticket)

        # Step 2: Validate guest eligibility
        self._validate_guest_eligibility(guest)

        # Step 3: Fetch Secret Party data and get guest_ingest object
        guest_ingest = self._get_secret_party_guest_ingest(guest)

        # Step 4: Validate product is a room product
        self._validate_room_product(guest_ingest.product)

        # Step 5: Find or assign room
        room = self._find_room(guest, guest_ingest.product)

        # Step 6: Determine OTP
        otp = self._determine_otp(guest)

        # Step 7: Display proposed changes
        self._display_proposed_changes(guest, room, otp)

        # Step 8: Confirm and apply changes
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run mode - no changes applied"))
            return

        if not force:
            self.stdout.write("Apply changes? [y/n/q]")
            choice = getch()
            if choice.lower() != 'y':
                self.stdout.write("Aborted")
                return

        # Step 9: Apply changes using the guest_ingest object
        self._apply_changes(guest, room, otp, guest_ingest)

        self.stdout.write(self.style.SUCCESS(
            f"Successfully assigned room {room.name_hotel} {room.number} to {guest.email}"
        ))
        logger.info(f"user_fix: Assigned room {room.name_hotel} {room.number} to guest {guest.email} (ticket {guest.ticket})")

    def _lookup_guest(self, search, search_by_ticket):
        """Lookup guest by email or ticket ID."""
        if search_by_ticket:
            guest_entries = Guest.objects.filter(ticket=search)
            if guest_entries.count() == 0:
                raise CommandError(f"No guest found with ticket {search}")
            if guest_entries.count() > 1:
                raise CommandError(f"Multiple guests found with ticket {search} - database corruption")
            return guest_entries.first()
        else:
            guest_entries = Guest.objects.filter(email=search)
            if guest_entries.count() == 0:
                raise CommandError(f"No guest found with email {search}")
            if guest_entries.count() > 1:
                ticket_list = ', '.join([g.ticket for g in guest_entries if g.ticket])
                raise CommandError(
                    f"Multiple guests found with email {search}. "
                    f"Please specify using --ticket flag with one of: {ticket_list}"
                )
            return guest_entries.first()

    def _validate_guest_eligibility(self, guest):
        """Check if guest is eligible for room fix."""
        # Check if guest already has a room
        if guest.room_number is not None:
            raise CommandError(
                f"Guest {guest.email} already has room assigned: {guest.hotel} {guest.room_number}"
            )

        if guest.room_set.count() > 0:
            room_list = ', '.join([f"{r.name_hotel} {r.number}" for r in guest.room_set.all()])
            raise CommandError(
                f"Guest {guest.email} already has Room objects assigned: {room_list}"
            )

        # Check if guest is intermediate in transfer chain
        transferred_tickets = set(
            Guest.objects.exclude(transfer='')
            .exclude(transfer__isnull=True)
            .values_list('transfer', flat=True)
        )

        if guest.ticket and guest.ticket in transferred_tickets:
            raise CommandError(
                f"Guest {guest.email} (ticket {guest.ticket}) is intermediate in a transfer chain. "
                "Only the final guest in a transfer chain should have a room. "
                "Consider using fix_transfer_chain command instead."
            )

    def _get_secret_party_guest_ingest(self, guest):
        """Fetch Secret Party data from cache or API and return SecretPartyGuestIngest object."""
        # Initialize client with API key if available (needed for API fetch if cache miss)
        sp_client = SecretPartyClient(api_key=roombaht_config.SP_API_KEY if roombaht_config.SP_API_KEY else None)

        try:
            # This will use cache if available, otherwise fetch from API
            sp_data = sp_client.get_all_active_and_transferred_tickets()
        except Exception as e:
            if not roombaht_config.SP_API_KEY:
                raise CommandError(
                    "No cached Secret Party data available and SP_API_KEY not configured. "
                    "Run system_check to populate cache or set SP_API_KEY to fetch from API."
                )
            raise CommandError(f"Failed to fetch Secret Party data: {e}")

        # Find ticket data and convert to SecretPartyGuestIngest object (like checks.py does)
        guest_ingest = None
        for ticket_data in sp_data:
            try:
                temp_ingest = SecretPartyGuestIngest.from_source(ticket_data, source_type='json')
                if temp_ingest.ticket_code == guest.ticket:
                    guest_ingest = temp_ingest
                    break
            except Exception as e:
                logger.warning(f"Error processing Secret Party ticket data: {e}")
                continue

        if guest_ingest is None:
            raise CommandError(
                f"Guest ticket {guest.ticket} not found in Secret Party data. "
                "Guest may not have a valid ticket or data may be stale."
            )

        return guest_ingest

    def _validate_room_product(self, sp_product):
        """Validate that the product is a room product."""
        room_products = set()
        for room_type, room_data in ROOM_LIST.items():
            room_products.update(room_data['rooms'])

        if sp_product not in room_products:
            raise CommandError(
                f"Product '{sp_product}' is not a room product. "
                "This guest does not qualify for room assignment."
            )

    def _find_room(self, guest, sp_product):
        """Find available room or manually placed room."""
        # Check for manually placed room first
        try:
            placed_room = Room.objects.get(sp_ticket_id=guest.ticket, guest=None)
            logger.info(
                f"Found manually placed room {placed_room.name_hotel} {placed_room.number} "
                f"for guest {guest.email} (ticket {guest.ticket})"
            )
            return placed_room
        except Room.DoesNotExist:
            pass  # No placed room, continue to find available
        except Room.MultipleObjectsReturned:
            raise CommandError(
                f"Multiple rooms with sp_ticket_id={guest.ticket} found - database corruption. "
                "Manual reconciliation required."
            )

        # Find available room via RoomAssignmentService
        room = RoomAssignmentService.find_room(sp_product)
        if not room:
            raise CommandError(
                f"No available rooms for product '{sp_product}'. "
                "Consider manually placing a room or waiting for availability."
            )

        logger.info(
            f"Found available room {room.name_hotel} {room.number} "
            f"for product '{sp_product}' for guest {guest.email}"
        )
        return room

    def _determine_otp(self, guest):
        """Determine OTP/JWT to use for guest."""
        if guest.jwt:
            return guest.jwt

        # Look for other guests with same email who have jwt
        other_guests = Guest.objects.filter(email=guest.email).exclude(jwt='')
        if other_guests.exists():
            otp = other_guests.first().jwt
            logger.info(f"Using existing JWT from another guest record with email {guest.email}")
            return otp

        # Generate new OTP
        otp = phrasing()
        logger.info(f"Generated new OTP for guest {guest.email}")
        return otp

    def _display_proposed_changes(self, guest, room, otp):
        """Display proposed changes to guest and room."""
        self.stdout.write("\nProposed changes:")
        self.stdout.write(f"\n✓ Guest {guest.email} (ticket {guest.ticket}):")
        self.stdout.write(f"    room_number: {guest.room_number} → {room.number}")
        self.stdout.write(f"    hotel: {guest.hotel} → {room.name_hotel}")

        will_login = room.name_hotel in roombaht_config.VISIBLE_HOTELS
        self.stdout.write(f"    can_login: {guest.can_login} → {will_login}")

        if not guest.jwt:
            self.stdout.write(f"    jwt: (empty) → {otp}")

        self.stdout.write(f"\n✓ Room {room.name_hotel} {room.number}:")
        self.stdout.write(f"    guest: {room.guest} → {guest.email}")
        self.stdout.write(f"    sp_ticket_id: '{room.sp_ticket_id}' → '{guest.ticket}'")
        self.stdout.write(f"    primary: '{room.primary}' → '{guest.name}'")
        self.stdout.write(f"    is_available: {room.is_available} → False")
        self.stdout.write("")

    def _apply_changes(self, guest, room, otp, guest_ingest):
        """Apply room assignment using GuestManagementService."""
        # Use the guest_ingest object we already have from Secret Party
        # Use GuestManagementService to apply the update
        guest_service = GuestManagementService()

        with transaction.atomic():
            guest_service.update_guest(guest_ingest, otp, room)
            logger.info(
                f"Applied room assignment: guest {guest.email} → room {room.name_hotel} {room.number}"
            )
