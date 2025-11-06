from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from reservations.models import Room, Guest
from reservations.management import getch, setup_logging
import reservations.config as roombaht_config
import logging


class TransferChainFixer:
    """Encapsulates logic for identifying and fixing transfer chain issues."""

    def __init__(self, logger):
        self.logger = logger

    def build_full_chain(self, ticket_id):
        """
        Build complete transfer chain from head to tail.
        Returns tuple: (chain_list, head_guest, tail_guest)
        where chain_list is ordered [head, intermediate(s), tail]

        Can start from any point in the chain.

        Raises CommandError if head or tail cannot be determined.
        """
        # Find the starting guest with this ticket
        try:
            start_guest = Guest.objects.get(ticket=ticket_id)
        except Guest.DoesNotExist:
            raise CommandError(f"No guest found with ticket {ticket_id}")
        except Guest.MultipleObjectsReturned:
            raise CommandError(f"Multiple guests found with ticket {ticket_id} - database corruption")

        # Walk BACKWARD (upstream) to find head
        # Head has Guest.transfer that is empty/None
        # Head's Guest.ticket appears in a downstream Guest.transfer
        current = start_guest
        upstream_chain = [current]

        while current.transfer and current.transfer != '':
            # Find the guest whose ticket matches current's transfer
            try:
                upstream_guest = Guest.objects.get(ticket=current.transfer)
                upstream_chain.insert(0, upstream_guest)
                current = upstream_guest
            except Guest.DoesNotExist:
                raise CommandError(f"Broken chain: ticket {current.transfer} not found (referenced by {current.ticket})")
            except Guest.MultipleObjectsReturned:
                raise CommandError(f"Multiple guests found with ticket {current.transfer} - database corruption")

        head = upstream_chain[0]

        # Verify head has no transfer (or empty transfer)
        if head.transfer and head.transfer != '':
            raise CommandError(f"Cannot find head: guest {head.email} (ticket {head.ticket}) still has transfer={head.transfer}")

        # Walk FORWARD (downstream) from the starting guest to find tail
        # Tail's Guest.ticket does NOT appear in any other Guest.transfer
        # Each intermediate's Guest.ticket should be in a downstream Guest.transfer
        current = start_guest
        downstream_chain = []

        while True:
            downstream_chain.append(current)

            # Find guest who has this ticket in their transfer field
            try:
                downstream_guest = Guest.objects.get(transfer=current.ticket)
                current = downstream_guest
            except Guest.DoesNotExist:
                # No one has this ticket in their transfer - this is the tail
                break
            except Guest.MultipleObjectsReturned:
                raise CommandError(f"Multiple guests have transfer={current.ticket} - database corruption")

        tail = current

        # Verify tail: no other guest should have tail's ticket in their transfer field
        if Guest.objects.filter(transfer=tail.ticket).exists():
            raise CommandError(f"Cannot find tail: guest {tail.email} (ticket {tail.ticket}) was transferred to someone else")

        # Build complete chain by combining upstream (before start) and downstream (after start)
        # Remove duplicates where they overlap (the start_guest)
        full_chain = upstream_chain.copy()
        for guest in downstream_chain:
            if guest not in full_chain:
                full_chain.append(guest)

        return full_chain, head, tail

    def find_tail(self, chain):
        """
        Identify the tail guest in a chain (current owner).
        The tail is the guest whose ticket does NOT appear in any other guest's transfer field.
        """
        # Get all tickets that have been transferred away
        transferred_tickets = set(Guest.objects.exclude(transfer='').exclude(transfer__isnull=True).values_list('transfer', flat=True))

        # Find guest in chain whose ticket is not in transferred_tickets
        for guest in reversed(chain):
            if guest.ticket not in transferred_tickets:
                return guest

        # If all tickets were transferred (shouldn't happen), return last guest
        return chain[-1] if chain else None

    def get_changes(self, chain, tail, orphan_action='ask', chosen_room=None):
        """
        Identify what needs to change to fix the chain.
        Returns list of (change_type, object, old_values, new_values, metadata) tuples.
        metadata can include 'is_placed_warning' for rooms with is_placed=True

        This method finds ALL Room objects that reference any guest in the chain
        and consolidates them to ONE room pointing to the tail guest.
        """
        changes = []
        intermediates = [g for g in chain if g != tail]

        # Collect ALL Room objects and Room locations that reference ANY guest in the entire chain
        # We need to track both:
        # 1. Room objects (via FK and sp_ticket_id)
        # 2. Guest.room_number/hotel fields (which might not have Room objects)

        all_chain_rooms = []  # List of (room, guest_index_in_chain) tuples
        room_locations = {}  # Track (hotel, room_number) -> {'rooms': [(room, idx)], 'guest_fields': [(guest, idx)]}

        for idx, guest in enumerate(chain):
            # Track Guest.room_number/hotel fields (original assignment indicator)
            if guest.room_number and guest.hotel:
                loc = (guest.hotel, guest.room_number)
                if loc not in room_locations:
                    room_locations[loc] = {'rooms': [], 'guest_fields': []}
                room_locations[loc]['guest_fields'].append((guest, idx))

            # Collect rooms via FK relationship
            for room in guest.room_set.all():
                room_tuple = (room, idx)
                if room not in [r[0] for r in all_chain_rooms]:
                    all_chain_rooms.append(room_tuple)
                    loc = (room.name_hotel, room.number)
                    if loc not in room_locations:
                        room_locations[loc] = {'rooms': [], 'guest_fields': []}
                    room_locations[loc]['rooms'].append((room, idx))

            # Find rooms by sp_ticket_id
            rooms_by_ticket = Room.objects.filter(sp_ticket_id=guest.ticket)
            for room in rooms_by_ticket:
                room_tuple = (room, idx)
                if room not in [r[0] for r in all_chain_rooms]:
                    all_chain_rooms.append(room_tuple)
                    loc = (room.name_hotel, room.number)
                    if loc not in room_locations:
                        room_locations[loc] = {'rooms': [], 'guest_fields': []}
                    # Don't re-add if already there from FK
                    if (room, idx) not in room_locations[loc]['rooms']:
                        room_locations[loc]['rooms'].append((room, idx))

        # Determine the ONE correct room location
        unique_locations = list(room_locations.keys())
        correct_room_loc = None

        if len(unique_locations) == 0:
            # No rooms found at all - this is OK, might be transfer chain with no room
            pass
        elif len(unique_locations) == 1:
            # Single room location - this is the correct one
            correct_room_loc = unique_locations[0]
        else:
            # Multiple different room locations - need to pick one
            if chosen_room is not None:
                # User already chose
                correct_room_loc = chosen_room
            else:
                # Determine which room to use:
                # PRIORITY 1: If one room has is_placed=True, it MUST be the correct room
                # PRIORITY 2: Otherwise, prefer room associated with HEAD guest (earliest in chain, idx=0)
                # PRIORITY 3: If still ambiguous, prompt user

                # First, check if ANY room has is_placed=True
                placed_locations = []
                for loc, loc_data in room_locations.items():
                    if any(room.is_placed for room, idx in loc_data.get('rooms', [])):
                        placed_locations.append(loc)

                if len(placed_locations) == 1:
                    # Exactly one is_placed=True room - this MUST be the correct one
                    correct_room_loc = placed_locations[0]
                elif len(placed_locations) > 1:
                    # Multiple is_placed=True rooms - need user to choose
                    changes.append(('choose_room', unique_locations, room_locations, {}))
                    return changes
                else:
                    # No is_placed=True rooms - fall back to HEAD preference
                    # Find location associated with head (idx 0)
                    head_locations = []
                    for loc, loc_data in room_locations.items():
                        # Check if this location has rooms or guest fields from head (idx 0)
                        if any(idx == 0 for room, idx in loc_data.get('rooms', [])) or \
                           any(idx == 0 for guest, idx in loc_data.get('guest_fields', [])):
                            head_locations.append(loc)

                    if len(head_locations) == 1:
                        # Unambiguous: head has exactly one room
                        correct_room_loc = head_locations[0]
                    elif len(head_locations) > 1:
                        # Multiple head rooms - need user choice
                        changes.append(('choose_room', unique_locations, room_locations, {}))
                        return changes
                    else:
                        # No head locations - fall back to earliest position
                        earliest_idx = min(idx for loc_data in room_locations.values()
                                         for room, idx in loc_data.get('rooms', []))

                        earliest_locations = []
                        for loc, loc_data in room_locations.items():
                            if any(idx == earliest_idx for room, idx in loc_data.get('rooms', [])):
                                earliest_locations.append(loc)

                        if len(earliest_locations) == 1:
                            correct_room_loc = earliest_locations[0]
                        else:
                            # Multiple at same position - need user choice
                            changes.append(('choose_room', unique_locations, room_locations, {}))
                            return changes

        # Clear intermediate guest fields
        for guest in intermediates:
            guest_changes = {}

            if guest.room_number is not None:
                guest_changes['room_number'] = (guest.room_number, None)
            if guest.hotel is not None:
                guest_changes['hotel'] = (guest.hotel, None)
            if guest.can_login:
                guest_changes['can_login'] = (True, False)

            if guest_changes:
                changes.append(('guest', guest, guest_changes, {}))

        # Process ALL Room objects - keep the correct one, mark others
        correct_room = None
        other_rooms = []

        for room, idx in all_chain_rooms:
            loc = (room.name_hotel, room.number)

            if correct_room_loc and loc == correct_room_loc:
                # This is THE room to keep - update it to point to tail
                correct_room = room
                room_changes = {
                    'guest': (room.guest.email if room.guest else None, tail.email if tail else None),
                    'sp_ticket_id': (room.sp_ticket_id, tail.ticket if tail else None),
                    'primary': (room.primary, tail.name if tail else ''),
                    'secondary': (room.secondary, ''),
                }

                # Add metadata for warnings and tail ticket
                metadata = {
                    'orphan_action': orphan_action,
                    'is_correct_room': True,
                    'new_guest_ticket': tail.ticket if tail else None
                }
                if room.is_placed:
                    metadata['is_placed_warning'] = True

                changes.append(('room', room, room_changes, metadata))
            else:
                # This is a duplicate/wrong room - mark for removal/deactivation
                other_rooms.append((room, idx))

                # Mark this room as duplicate that should be removed
                room_changes = {
                    'guest': (room.guest.email if room.guest else None, None),
                    'sp_ticket_id': (room.sp_ticket_id, ''),
                    'is_available': (room.is_available, True),
                    'primary': (room.primary, ''),
                    'secondary': (room.secondary, ''),
                }

                metadata = {'is_duplicate': True}
                if room.is_placed:
                    metadata['is_placed_warning'] = True

                changes.append(('room', room, room_changes, metadata))

        # Fix tail guest room assignment if needed
        if tail and correct_room_loc:
            tail_changes = {}
            hotel, room_number = correct_room_loc

            if tail.room_number != room_number:
                tail_changes['room_number'] = (tail.room_number, room_number)
            if tail.hotel != hotel:
                tail_changes['hotel'] = (tail.hotel, hotel)

            if tail_changes:
                changes.append(('guest', tail, tail_changes, {}))

        return changes

    def apply_changes(self, changes, orphan_action='ask', tail_guest=None):
        """
        Apply changes with transaction wrapping.
        Returns list of (success, message) tuples.

        tail_guest: The tail Guest object to use when updating rooms
        """
        results = []

        with transaction.atomic():
            for change in changes:
                change_type = change[0]

                # Skip warnings - they're just for display
                if change_type == 'warning':
                    continue

                obj = change[1]
                metadata = change[3] if len(change) > 3 else {}

                if change_type == 'guest':
                    guest_changes = change[2]
                    for field, (old_val, new_val) in guest_changes.items():
                        setattr(obj, field, new_val)
                    obj.save()
                    results.append((True, f"Updated Guest {obj.email} (ticket {obj.ticket})"))

                elif change_type == 'room':
                    room = obj
                    room_changes = change[2]
                    action = metadata.get('orphan_action', orphan_action)
                    is_duplicate = metadata.get('is_duplicate', False)

                    # Update all fields
                    if 'guest' in room_changes:
                        new_guest_email = room_changes['guest'][1]
                        if new_guest_email:
                            # Use the tail_guest object if email matches, otherwise look up by ticket
                            if tail_guest and tail_guest.email == new_guest_email:
                                new_guest = tail_guest
                            else:
                                # Get by ticket to avoid ambiguity with duplicate emails
                                new_guest_ticket = metadata.get('new_guest_ticket')
                                if new_guest_ticket:
                                    new_guest = Guest.objects.get(ticket=new_guest_ticket)
                                else:
                                    # Fallback - should not happen but handle gracefully
                                    new_guest = tail_guest
                        else:
                            new_guest = None
                        room.guest = new_guest

                    if 'sp_ticket_id' in room_changes:
                        room.sp_ticket_id = room_changes['sp_ticket_id'][1]

                    if 'primary' in room_changes:
                        room.primary = room_changes['primary'][1]

                    if 'secondary' in room_changes:
                        room.secondary = room_changes['secondary'][1]

                    if 'is_available' in room_changes:
                        room.is_available = room_changes['is_available'][1]

                    room.save()

                    if is_duplicate:
                        results.append((True, f"Cleared duplicate Room {room.name_hotel} {room.number}"))
                    elif room.guest is None:
                        if room.is_available:
                            results.append((True, f"Updated Room {room.name_hotel} {room.number}, marked available"))
                        else:
                            results.append((True, f"Updated Room {room.name_hotel} {room.number}, left as orphan"))
                    else:
                        results.append((True, f"Updated Room {room.name_hotel} {room.number}"))

                else:
                    raise CommandError(f"Unknown change type for object")

        return results


class Command(BaseCommand):
    help = 'Fix transfer chains ensuring only tail guest has room assigned'

    def add_arguments(self, parser):
        parser.add_argument('ticket_ids',
                            nargs='+',
                            help='Ticket ID(s) (any point in chain) - space separated')
        parser.add_argument('--dry-run', '-d',
                            action='store_true',
                            help='Show changes without applying')
        parser.add_argument('--force', '-f',
                            action='store_true',
                            help='Skip y/n confirmation prompt')

    def handle(self, *args, **kwargs):
        self.verbosity = kwargs.get('verbosity', 1)
        setup_logging(self)
        logger = logging.getLogger(__name__)

        ticket_ids = kwargs['ticket_ids']
        dry_run = kwargs['dry_run']
        force = kwargs['force']

        fixer = TransferChainFixer(logger)

        # Process each ticket
        for ticket_id in ticket_ids:
            if self.verbosity >= 2:
                self.stdout.write(f"\n{'='*80}")
                self.stdout.write(f"Processing ticket: {ticket_id}")
                self.stdout.write('='*80)

            try:
                # Build the chain
                chain, head, tail = fixer.build_full_chain(ticket_id)

                if self.verbosity >= 1:
                    self.stdout.write(f"\nTransfer Chain for ticket {ticket_id}:")
                    for i, g in enumerate(chain):
                        prefix = "  "
                        if g == head:
                            label = "[HEAD] "
                        elif g == tail:
                            label = "[TAIL - should have room] "
                            prefix = self.style.SUCCESS("  → ")
                        else:
                            label = "[INTERMEDIATE] "

                        guest_info = f"{label}{g.email} ({g.ticket})"

                        # Highlight the tail
                        if g == tail:
                            self.stdout.write(self.style.SUCCESS(f"{prefix}{guest_info}"))
                        else:
                            self.stdout.write(f"{prefix}{guest_info}")

                # Verify tail
                verified_tail = fixer.find_tail(chain)
                if verified_tail != tail:
                    self.stdout.write(self.style.WARNING(
                        f"  Tail mismatch: expected {tail.email if tail else 'None'}, found {verified_tail.email if verified_tail else 'None'}"
                    ))
                    tail = verified_tail

                # Get changes needed
                # We'll ask about orphan action and room choice if needed
                orphan_action = None
                chosen_room = None
                changes = fixer.get_changes(chain, tail, orphan_action='ask', chosen_room=chosen_room)

                # Check if user needs to choose a room
                if changes and changes[0][0] == 'choose_room':
                    available_locations = changes[0][1]
                    room_locations = changes[0][2]

                    # Find default room: prefer is_placed=True rooms
                    default_idx = 0
                    for i, loc in enumerate(available_locations):
                        loc_data = room_locations[loc]
                        # Check if any room at this location has is_placed=True
                        for room, idx in loc_data.get('rooms', []):
                            if room.is_placed:
                                default_idx = i
                                break
                        if default_idx == i:
                            break

                    self.stdout.write(self.style.WARNING("\n⚠️  Multiple room locations found in transfer chain:"))
                    for i, loc in enumerate(available_locations, 1):
                        hotel, room_number = loc
                        # Show which guest(s) in chain have this room
                        loc_data = room_locations[loc]
                        guest_info = []
                        is_placed_in_loc = False
                        # Show from guest_fields (original ownership) and rooms (current FK)
                        for guest, idx in loc_data.get('guest_fields', []):
                            guest_info.append(f"{guest.email} (position {idx}, guest_field)")
                        for room, idx in loc_data.get('rooms', []):
                            if room.is_placed:
                                is_placed_in_loc = True
                            guest_info.append(f"{chain[idx].email} (position {idx}, room_fk)")

                        default_marker = " [DEFAULT]" if (i - 1) == default_idx else ""
                        is_placed_marker = " [is_placed=True]" if is_placed_in_loc else ""
                        self.stdout.write(f"  {i}. {hotel} {room_number}{default_marker}{is_placed_marker}")
                        self.stdout.write(f"     Associated with: {', '.join(guest_info)}")

                    self.stdout.write("  q. Quit")
                    default_prompt = default_idx + 1
                    self.stdout.write(f"\nWhich room should be kept? [1-{len(available_locations)}/q] (default: {default_prompt}): ", ending='')

                    choice = getch()
                    self.stdout.write(choice)  # Echo the choice

                    if choice.lower() == 'q':
                        self.stdout.write(self.style.WARNING("\nAborting fix_transfer_chain"))
                        return
                    elif choice == '\r' or choice == '\n' or choice == '':
                        # Use default
                        chosen_room = available_locations[default_idx]
                    else:
                        try:
                            choice_idx = int(choice) - 1
                            if 0 <= choice_idx < len(available_locations):
                                chosen_room = available_locations[choice_idx]
                            else:
                                raise CommandError(f"Invalid choice: {choice}")
                        except ValueError:
                            raise CommandError(f"Invalid choice: {choice}")

                    # Regenerate changes with chosen room
                    changes = fixer.get_changes(chain, tail, orphan_action='ask', chosen_room=chosen_room)

                # Display changes (before prompting for orphan action)
                if not changes:
                    if self.verbosity >= 1:
                        self.stdout.write(self.style.SUCCESS("\n  No changes needed - chain is correct!"))
                    continue

                # Check for is_placed warnings
                has_placed_warning = any(
                    change[0] == 'room' and len(change) > 3 and change[3].get('is_placed_warning', False)
                    for change in changes
                )

                if has_placed_warning:
                    self.stdout.write(self.style.WARNING("\n⚠️  WARNING: Some rooms have is_placed=True"))
                    self.stdout.write(self.style.WARNING("   These rooms have been physically placed and may require manual intervention."))
                    for change in changes:
                        if change[0] == 'room' and len(change) > 3 and change[3].get('is_placed_warning', False):
                            room = change[1]
                            self.stdout.write(self.style.WARNING(f"   - {room.name_hotel} {room.number}"))

                # Always display proposed changes if we have verbosity >= 1 OR not in dry-run/force mode
                if self.verbosity >= 1 or (not dry_run and not force):
                    self.stdout.write("\nProposed Changes:")

                    for change in changes:
                        change_type = change[0]
                        metadata = change[3] if len(change) > 3 else {}

                        if change_type == 'guest':
                            guest = change[1]
                            guest_changes = change[2]
                            self.stdout.write(f"\n  Guest {guest.email} (ticket {guest.ticket}):")
                            for field, (old_val, new_val) in guest_changes.items():
                                old_display = f"'{old_val}'" if old_val is not None else 'None'
                                new_display = f"'{new_val}'" if new_val is not None else 'None'
                                self.stdout.write(self.style.MIGRATE_LABEL(
                                    f"    {field}: {old_display} → {new_display}"
                                ))

                        elif change_type == 'room':
                            room = change[1]
                            room_changes = change[2]
                            action = metadata.get('orphan_action', 'unknown')
                            is_duplicate = metadata.get('is_duplicate', False)
                            is_correct = metadata.get('is_correct_room', False)

                            room_header = f"\n  Room {room.name_hotel} {room.number}:"
                            if is_correct:
                                room_header += self.style.SUCCESS(" [CORRECT ROOM - will be assigned to tail]")
                            elif is_duplicate:
                                room_header += self.style.WARNING(" [DUPLICATE - will be cleared]")
                            if metadata.get('is_placed_warning', False):
                                room_header += self.style.WARNING(" [is_placed=True]")
                            self.stdout.write(room_header)

                            for field, (old_val, new_val) in room_changes.items():
                                old_display = f"'{old_val}'" if old_val is not None and old_val != '' else 'None'
                                new_display = f"'{new_val}'" if new_val is not None and new_val != '' else 'None'
                                self.stdout.write(self.style.MIGRATE_LABEL(
                                    f"    {field}: {old_display} → {new_display}"
                                ))

                # Check if any rooms would become orphaned
                has_orphan_rooms = any(
                    change[0] == 'room' and change[2].get('guest', (None, None))[1] is None
                    for change in changes
                )

                if has_orphan_rooms and not dry_run and orphan_action is None:
                    self.stdout.write("\nSome rooms will lose their guest assignment. How should we handle orphaned rooms?")
                    self.stdout.write("  1. Mark as available (is_available=True)")
                    self.stdout.write("  2. Leave as orphan (no guest, not available)")
                    self.stdout.write("  q. Quit")
                    self.stdout.write("Select option [1/2/q]: ", ending='')

                    choice = getch()
                    self.stdout.write(choice)  # Echo the choice

                    if choice == '1':
                        orphan_action = 'mark_available'
                    elif choice == '2':
                        orphan_action = 'leave_orphan'
                    elif choice.lower() == 'q':
                        self.stdout.write(self.style.WARNING("\nAborting fix_transfer_chain"))
                        return
                    else:
                        raise CommandError(f"Invalid choice: {choice}")

                    # Regenerate changes with chosen action
                    changes = fixer.get_changes(chain, tail, orphan_action=orphan_action, chosen_room=chosen_room)

                # Apply changes if not dry run
                if dry_run:
                    self.stdout.write(self.style.WARNING("\nDRY RUN - No changes applied"))
                else:
                    # Prompt for confirmation unless --force
                    if not force:
                        self.stdout.write("\nApply these changes? [y/n/q (to stop process)]", ending=' ')
                        choice = getch()
                        self.stdout.write(choice)  # Echo the choice

                        if choice.lower() == 'q':
                            self.stdout.write(self.style.WARNING("\nAborting fix_transfer_chain"))
                            return
                        elif choice.lower() != 'y':
                            self.stdout.write(self.style.WARNING("\nSkipping this ticket"))
                            continue

                    # Apply the changes
                    results = fixer.apply_changes(changes, orphan_action=orphan_action or 'leave_orphan', tail_guest=tail)

                    self.stdout.write("")  # Blank line
                    for success, message in results:
                        if success:
                            self.stdout.write(self.style.SUCCESS(f"  ✓ {message}"))
                        else:
                            self.stdout.write(self.style.ERROR(f"  ✗ {message}"))

                    self.stdout.write(self.style.SUCCESS(f"\nCompleted fixes for ticket {ticket_id}"))

            except CommandError as e:
                self.stdout.write(self.style.ERROR(f"\nError processing ticket {ticket_id}: {e}"))
                if not force:
                    self.stdout.write("Continue with next ticket? [y/n]", ending=' ')
                    choice = getch()
                    self.stdout.write(choice)
                    if choice.lower() != 'y':
                        return
                continue
            except Exception as e:
                logger.exception(f"Unexpected error processing ticket {ticket_id}")
                self.stdout.write(self.style.ERROR(f"\nUnexpected error processing ticket {ticket_id}: {e}"))
                if not force:
                    self.stdout.write("Continue with next ticket? [y/n]", ending=' ')
                    choice = getch()
                    self.stdout.write(choice)
                    if choice.lower() != 'y':
                        return
                continue

        self.stdout.write(self.style.SUCCESS(f"\n{'='*80}"))
        self.stdout.write(self.style.SUCCESS("All tickets processed"))
