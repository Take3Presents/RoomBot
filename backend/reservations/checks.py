from django.core.checks import Error, Warning, Info, register, Tags
from django.core.exceptions import MultipleObjectsReturned
from fuzzywuzzy import fuzz
from reservations.models import Room, Guest
from reservations import config as roombaht_config
import json
from datetime import datetime, timedelta
from pathlib import Path
from reservations.secret_party import SecretPartyClient
from reservations.ingest_models import SecretPartyGuestIngest
from reservations.constants import ROOM_LIST

def room_guest_name_mismatch(room):
    if not room.guest:
        return False

    for name in room.occupants():
        if fuzz.ratio(room.guest.name, name) >= roombaht_config.NAME_FUZZ_FACTOR:
            return False

    return True

def ticket_chain(p_guest):
    if not p_guest.transfer or p_guest.transfer == '':
        return [p_guest]

    # Use the model implementation to build the forward chain starting from
    # the ticket referenced by this guest's transfer. Guest.chain returns a
    # list ordered from the start ticket toward the tail, so reverse it to
    # match the previous ordering ([tail, ..., start]).
    forward_chain = Guest.chain(p_guest.transfer)
    combined = [p_guest] + forward_chain
    return list(reversed(combined))


@register(Tags.database, deploy=True)
def guest_drama_check(app_configs, **kwargs):
    errors = []
    guests = Guest.objects.all()


    for guest in guests:
        # every guest record should be updated when jwt is changed. this check
        # should only trigger as side effect of orm manipulation
        if guest.jwt == '' and guest.can_login:
            errors.append(Warning(f"Guest {guest.email} has an empty jwt field!",
                                  hint="Have user reset password, or use user_edit",
                                  obj=guest))


        # guests will be set to login when created during secretparty import
        # according to the VISIBLE_HOTELS config. if this changes after a
        # guest was imported, or there was some orm fuckery, this check will trigger
        if guest.room_set.count() == 1 and \
           guest.hotel in roombaht_config.VISIBLE_HOTELS \
           and not guest.can_login:
            errors.append(Warning(f"Guest {guest.email} should be able to login!",
                                  hint="Use user_edit or update_logins to fix",
                                  obj=guest))

        # should only occur due to orm fuckery, and potentially odd airtable intake
        if guest.ticket and Guest.objects.filter(ticket=guest.ticket).count() > 1:
            errors.append(Error(f"Guest {guest.email}, ticket {guest.ticket} shared with other users",
                                obj=guest))

    multi_room = [','.join([str(x) for x in Guest.objects.all() if x.room_set.count() > 1])]
    if len([x for x in multi_room if len(x) > 0]) > 0:
        errors.append(Error(f"Guest records with multiple associated rooms {multi_room}"))

    # Check for tickets assigned to multiple room entries
    ticket_counts = {}
    for room in Room.objects.exclude(sp_ticket_id__isnull=True).exclude(sp_ticket_id=''):
        ticket = room.sp_ticket_id
        if ticket not in ticket_counts:
            ticket_counts[ticket] = []
        ticket_counts[ticket].append(f"{room.name_hotel} {room.number}")

    for ticket, rooms in ticket_counts.items():
        if len(rooms) > 1:
            errors.append(Error(f"Ticket {ticket} assigned to multiple rooms: {', '.join(rooms)}",
                                hint="Manually reconcile room assignments"))

    # Check for tickets assigned to multiple guest entries
    for guest in guests:
        if guest.ticket and Guest.objects.filter(ticket=guest.ticket).count() > 1:
            duplicate_guests = Guest.objects.filter(ticket=guest.ticket)
            guest_list = ', '.join([f"{g.email} (id={g.id})" for g in duplicate_guests])
            errors.append(Error(f"Ticket {guest.ticket} assigned to multiple guest entries: {guest_list}",
                                hint="Manually reconcile guest records"))

    return errors

@register(Tags.database, deploy=True)
def room_drama_check(app_configs, **kwargs):
    errors = []
    rooms = Room.objects.all()
    for room in rooms:
        # for every room, if there is a guest, make sure the number
        # on the guest record matches the actual room number
        if room.guest and room.number != room.guest.room_number:
            errors.append(Error(f"Room/guest number mismatch {room.name_hotel} {room.number} / {room.guest.email} {room.guest.hotel} {room.guest.room_number}",
                                hint='Manually reconcile room/guest numbers', obj=room))

        if room_guest_name_mismatch(room):
            errors.append(Error(f"Room/guest name mismatch {room.name_hotel} {room.number} {room.primary} / {room.guest.name}",
                                hint='Manually reconcile room/guest names', obj=room))

        # side effect of transferring placed rooms
        if room.sp_ticket_id:
            guest = None
            alt_msg = ''
            try:
                guest = Guest.objects.get(ticket=room.sp_ticket_id)
                if room.number != guest.room_number:
                    errors.append(Error(f"Ticket {room.sp_ticket_id} room/guest number mismatch {room.number} / {guest.room_number}",
                                        hint='Manually reconcile room/guest numbers for specified ticket', obj=room))

                if room_guest_name_mismatch(room):
                    errors.append(Error(f"Room {room.name_hotel} {room.number} {room.sp_ticket_id} room/guest name mismatch {room.primary} / {guest.name}",
                                        hint='Manually reconcile room/guest names for specified ticket',
                                        obj=room))

            except Guest.DoesNotExist:
                errors.append(Error(f"Original owner of {room.name_hotel} {room.number} with ticket {room.sp_ticket_id} not found",
                                    hint='Good luck, I guess?', obj=room))
            except MultipleObjectsReturned:
                errors.append(Error(f"Multiple guests found with ticket {room.sp_ticket_id} for room {room.name_hotel} {room.number}",
                                    hint='Database corruption - manual reconciliation required', obj=room))

            if room.guest is None:
                errors.append(Error(f"Room {room.number} ({room.name_hotel}) sp_ticket_id {room.sp_ticket_id} missing guest",
                                    hint='Manually reconcile w/ sources of truth', obj=room))

            if room.guest is not None and room.number != room.guest.room_number \
               and room.primary != room.guest.name \
                   and guest is not None:
                try:
                    guest = Guest.objects.get(transfer=room.sp_ticket_id)
                    if room.number != guest.room_number:
                        errors.append(Error(f"Room {room.number} ({room.name_hotel}) Ticket {room.sp_ticket_id} transfer {guest.ticket} room/guest number mismatch {room.number} / {guest.room_number}",
                                            hint='Manually reconcile room/guest numbers for specified ticket(s)',
                                            obj=room))

                    if room.primary != guest.name:
                        errors.append(Error(f"Room {room.number} ({room.name_hotel}) Ticket {room.sp_ticket_id} transfer {guest.ticket} room/guest name mismatch {room.primary} / {guest.name}",
                                            hint='Manually reconcile room/guest names for specified ticket(s)', obj=room))

                except Guest.DoesNotExist:
                    errors.append(Error(f"Room {room.number} ({room.name_hotel}) Ticket {room.sp_ticket_id} transfer owner not found",
                                        hint='Good luck, I guess?', obj=room))
                except MultipleObjectsReturned:
                    errors.append(Error(f"Multiple guests found with transfer={room.sp_ticket_id} for room {room.name_hotel} {room.number}",
                                        hint='Database corruption - manual reconciliation required', obj=room))

        # general corruption which could bubble up during orm/sql manipulation
        missing = []
        if room.check_in is None:
            missing.append('check_in')
        if room.check_out is None:
            missing.append('check_out')

        if missing:
            pretty = [m.replace('_', '-') for m in missing]
            if len(pretty) == 1:
                msg = f"Room {room.name_hotel} {room.number} has blank {pretty[0]} date"
            else:
                msg = f"Room {room.name_hotel} {room.number} has blank {' and '.join(pretty)} dates"

            errors.append(Warning(msg,
                                  hint='Use commands room_fix for a single room or update_dates for multiple rooms',
                                  obj=room))


    return errors


@register(Tags.database, deploy=True)
def secret_party_data_check(app_configs, **kwargs):
    """Check database state against Secret Party source data to detect missing room assignments."""

    if not roombaht_config.SP_SYSTEM_CHECKS:
        return [Info("Skipping secret party data check",
                     hint='This check does not run in tests or CI')]

    errors = []

    # Build set of all room product names from ROOM_LIST
    room_products = set()
    for room_type, room_data in ROOM_LIST.items():
        room_products.update(room_data['rooms'])

    # Set up cache directory and file (expand ~ to home directory)
    cache_dir = Path(roombaht_config.CHECK_CACHE_DIR).expanduser()
    cache_file = cache_dir / 'secret_party_check.json'
    cache_max_age = timedelta(hours=1)  # Cache for 1 hour

    sp_data = None

    # Try to load from cache first
    if cache_file.exists():
        try:
            cache_mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
            if datetime.now() - cache_mtime < cache_max_age:
                with open(cache_file, 'r') as f:
                    sp_data = json.load(f)
        except (json.JSONDecodeError, IOError, OSError) as e:
            errors.append(Warning(
                f"Failed to read cache file {cache_file}: {e}",
                hint="Cache will be refreshed from Secret Party API"
            ))

    # Fetch from API if cache miss or expired
    if sp_data is None:
        if not roombaht_config.SP_API_KEY:
            errors.append(Warning(
                "SP_API_KEY not configured - skipping Secret Party data check",
                hint="Set ROOMBAHT_SP_API_KEY environment variable to enable this check"
            ))
            return errors

        try:
            client = SecretPartyClient(roombaht_config.SP_API_KEY)
            sp_data = client.get_all_active_and_transferred_tickets()

            # Write to cache
            try:
                cache_dir.mkdir(parents=True, exist_ok=True)
                with open(cache_file, 'w') as f:
                    json.dump(sp_data, f)
                errors.append(Info(
                    f"Secret Party data cached to {cache_file}",
                    hint="Cache is valid for 1 hour"
                ))
            except Exception as cache_error:
                errors.append(Warning(
                    f"Failed to write cache to {cache_file}: {cache_error}",
                    hint="Check directory permissions. Data will be re-fetched on next check."
                ))

        except Exception as e:
            errors.append(Warning(
                f"Failed to fetch Secret Party data: {e}",
                hint="Check API key and network connectivity. System check will be skipped."
            ))
            return errors

    # Process Secret Party data and compare with database
    transferred_tickets = set(Guest.objects.exclude(transfer='').exclude(transfer__isnull=True).values_list('transfer', flat=True))

    for ticket_data in sp_data:
        try:
            guest_obj = SecretPartyGuestIngest.from_source(ticket_data, source_type='json')

            # Skip if not a room product
            if guest_obj.product not in room_products:
                continue

            ticket_code = guest_obj.ticket_code

            # Check if this ticket was transferred away (intermediate in chain)
            if ticket_code in transferred_tickets:
                continue  # Intermediate guests shouldn't have rooms

            # This is a tail guest with a room product - they should have a room assignment
            try:
                guest = Guest.objects.get(ticket=ticket_code)

                # Check if they have a room assigned
                if guest.room_number is None and guest.room_set.count() == 0:
                    errors.append(Error(
                        f"(ticket {ticket_code}) has room product '{guest_obj.product}' in Secret Party but no room assigned in database",
                        hint="Room assignment may have failed during ingestion. Consider re-running ingestion or manual assignment.",
                        obj=guest
                    ))
                elif guest.room_number is not None and guest.room_set.count() == 0:
                    errors.append(Error(
                        f"(ticket {ticket_code}) has room_number='{guest.room_number}' but no Room object with associated guest",
                        hint="Database inconsistency - room_number is set but Room.guest is missing.",
                        obj=guest
                    ))

            except Guest.DoesNotExist:
                errors.append(Warning(
                    f"Ticket {ticket_code} with room product '{guest_obj.product}' exists in Secret Party but not in database",
                    hint="Guest may not have been ingested yet. Fetch secret party data via command or admin page."
                ))
            except Guest.MultipleObjectsReturned:
                errors.append(Error(
                    f"Multiple Guest records found for ticket {ticket_code}",
                    hint="Database corruption - duplicate ticket codes exist."
                ))

        except Exception as e:
            errors.append(Warning(
                f"Error processing Secret Party ticket data: {e}",
                hint="Check data format and ingestion models"
            ))

    return errors


@register(Tags.database, deploy=True)
def intermediate_transfer_guest_check(app_configs, **kwargs):
    """Check for intermediate guest records in transfer chains that incorrectly have rooms assigned."""
    errors = []

    # Find guests whose tickets WERE transferred to someone else
    transferred_tickets = set(Guest.objects.exclude(transfer='').exclude(transfer__isnull=True).values_list('transfer', flat=True))
    intermediate_guests = Guest.objects.filter(ticket__in=transferred_tickets)

    for guest in intermediate_guests:
        # Intermediate guests should NOT have rooms assigned
        if guest.room_number is not None:
            errors.append(Error(
                f"Intermediate transfer guest {guest.email} (ticket {guest.ticket}, was transferred to someone else) has room_number '{guest.room_number}'",
                hint="Only the final guest in a transfer chain should have a room. Check transfer processing.",
                obj=guest
            ))

        if guest.room_set.count() > 0:
            room_list = ', '.join([f"{r.name_hotel} {r.number}" for r in guest.room_set.all()])
            errors.append(Error(
                f"Intermediate transfer guest {guest.email} (ticket {guest.ticket}, was transferred to someone else) has Room objects assigned: {room_list}",
                hint="Only the final guest in a transfer chain should have associated Room. Check transfer processing.",
                obj=guest
            ))

    return errors
