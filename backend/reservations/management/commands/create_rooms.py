import logging
import re
import sys
from fuzzywuzzy import fuzz
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from pydantic import ValidationError
import reservations.config as roombaht_config
from reservations.helpers import ingest_csv
from reservations.models import Room, Guest, Staff
from reservations.ingest_models import RoomPlacementListIngest
from reservations.management import getch, setup_logging

logging.basicConfig(stream=sys.stdout, level=roombaht_config.LOGLEVEL)
logger = logging.getLogger('create_rooms')

def debug(msg, args):
    if args.get('verbosity', 1) >= 2:
        cmd.stdout.write(msg)

def guest_changes(guest):
    dirty_fields = guest.get_dirty_fields(verbose=True)
    msg = f"{guest.email} {'changes' if len(dirty_fields) > 0 else 'changed'}\n"
    for field, values in dirty_fields.items():
        saved = values['saved']
        msg = f"{msg}    {field} {saved} -> {values['current']}\n"

    return msg

def room_changes(room):
    msg = f"{room.name_hotel:9}{room.number:4} changes\n"
    for field, values in room.get_dirty_fields(verbose=True, check_relationship=True).items():
        saved = values['saved']
        if room.guest and field == 'primary':
            saved = f"{saved} (owner {room.guest.name})"
        msg = f"{msg}    {field} {saved} -> {values['current']}\n"

    return msg

def create_rooms_main(cmd, args):
    rooms_file = args['rooms_file']
    hotel = None
    if args['hotel_name'].lower() == 'ballys':
        hotel = "Ballys"
    elif args['hotel_name'].lower() == 'nugget':
        hotel = 'Nugget'
    else:
        raise Exception(f"Unknown hotel name {args['hotel_name']} specified")

    rooms = {}
    _rooms_fields, rooms_rows = ingest_csv(rooms_file)
    rooms_import_list = []
    dupe_rooms = []
    dupe_tickets = []
    sp_ticket_pattern = re.compile(r'^[A-Z0-9]{6}$')
    for r in rooms_rows:
        try:
            room_data = RoomPlacementListIngest(**r)
            if len([x for x in rooms_import_list if x.room == room_data.room]) > 0:
                dupe_rooms.append(str(room_data.room))

            if room_data.ticket_id_in_secret_party and \
               len([x for x in rooms_import_list if x.ticket_id_in_secret_party == room_data.ticket_id_in_secret_party]) > 0:
                dupe_tickets.append(room_data.ticket_id_in_secret_party)

            rooms_import_list.append(room_data)
        except ValidationError as e:
            cmd.stdout.write(cmd.style.ERROR(f"Validation error for row {e}"))

    if len(dupe_rooms) > 0:
        raise Exception(f"Duplicate room(s) {','.join(dupe_rooms)} in CSV, refusing to process file")

    if len(dupe_tickets) > 0:
        raise Exception(f"Duplicate ticket id(s) {','.join(dupe_tickets)} in CSV, refusing to process file")

    debug(f"read in {len(rooms_rows)} rooms for {hotel}", args)

    processed_rooms = []
    for elem in rooms_import_list:
        if len(args['only_room']) > 0 and str(elem.room) not in args['only_room']:
            continue

        room = None
        room_update = False
        try:
            room = Room.objects.get(number=elem.room, name_hotel=hotel)
            room_update = True
        except Room.DoesNotExist:
            # some things are not mutable
            # * room features
            # * room number
            # * hotel
            # * room type
            room_name = Room.derive_room_name(hotel, elem.room_code)
            if not room_name:
                cmd.stdout.write(cmd.style.ERROR(f"Unknown room code {elem.room_code} in {hotel} {elem.room}"))
                continue

            room = Room(name_take3=room_name,
                        name_hotel=hotel,
                        number=elem.room)

            try:
                features = elem.room_features.lower()
            except KeyError:
                features = []

            if 'hearing accessible' in features:
                room.is_hearing_accessible = True
            if 'ada' in features:
                room.is_ada = True
            if 'lakeview' in features or 'lake view' in features:
                room.is_lakeview = True
            if 'mountainview' in features or 'mountain view' in features:
                room.is_mountainview = True

        if elem.placed_by_roombaht and not room.placed_by_roombot:
            room.placed_by_roombot = True
            room.is_placed = False
            room.is_available = True

            if room.name_hotel in roombaht_config.VISIBLE_HOTELS:
                room.is_swappable = True

        elif not elem.placed_by_roombaht and room.placed_by_roombot:
            room.placed_by_roombot = False
            room.is_available = False
            room.is_swappable = False

        # check-in/check-out are only adjustable via airtable
        if elem.check_in_date == '' and args['default_check_in']:
            room.check_in = args['default_check_in']
        else:
            room.check_in = elem.check_in_date

        if elem.check_out_date == '' and args['default_check_out']:
            room.check_out = args['default_check_out']
        else:
            room.check_out = elem.check_out_date

        # Cannot mark a room as non available based on being set to roombaht
        #   in airtable if it already actually assigned, but you can mark
        #   a room as non available/swappable if it is not assigned yet
        if elem.placed_by == '' and not room.is_special and not room.is_available:
            if not room.guest and room.is_swappable:
                room.is_swappable = False
            else:
                if elem.ticket_id_in_secret_party == '':
                    debug(f"Room {room.number}, placed by roombot, being skipped, as it is marked as available in airtable", args)
                    continue

                cmd.stdout.write(cmd.style.WARNING(f"Room {room.number}, placed by roombot, showing as having ticket in airtable"))

        # the following per-guest stuff gets a bit more complex
        # TODO: Note that as we normalize names via .title() to remove chances of capitalization
        #       drama we lose the fact that some folk have mixed capitalization names i.e.
        #       Name McName and I guess we need to figure out how to handle that
        primary_name = None
        if elem.first_name_resident != '':
            primary_name = elem.first_name_resident
            if elem.last_name_resident == '':
                cmd.stdout.write(cmd.style.WARNING(f"Room {room.number} has no last name"))
            else:
                primary_name = f"{primary_name} {elem.last_name_resident}"

            if room.primary != primary_name.title():
                fuzziness = fuzz.ratio(room.primary, primary_name)
                if room.guest and room.guest.transfer:
                    trans_guest = room.guest.chain(room.guest.transfer)[-1]
                    if elem.ticket_id_in_secret_party == room.guest.ticket:
                        guest_fuzziness = fuzz.ratio(room.guest.name, primary_name.title())
                        if guest_fuzziness >= args['fuzziness']:
                            debug(cmd.style.SUCCESS(f"Updating primary name for {room.number} transfer {room.guest.transfer}"
                                                    f" {room.primary} -> {primary_name}, as it matches associated guest name"
                                                    f" (fuzziness{fuzziness} outside threshold of {args['fuzziness']}"), args)
                            room.primary = primary_name.title()

                    elif trans_guest.name == primary_name.title():
                        cmd.stdout.write(cmd.style.WARNING(
                            f"Room {room.number} ignoring airtable due to transfer {room.guest.transfer}"))
                        continue
                    else:
                        if fuzziness < args['fuzziness']:
                            room.primary = primary_name.title()
                        else:
                            debug(cmd.style.SUCCESS(f"Room {room.number} updating primary name"
                                                    f" {room.primary}->{primary_name} ({fuzziness}"
                                                    f" fuzziness within threshold of {args['fuzziness']}"), args)
                else:
                    if fuzziness < args['fuzziness']:
                        room.primary = primary_name.title()
                    else:
                        cmd.stdout.write(cmd.style.SUCCESS(f"Not updating primary name for {room.number}"
                                                           f" {room.primary}->{primary_name} ({fuzziness}"
                                                           f" fuzziness within threshold of {args['fuzziness']}"))

            if elem.placed_by == '':
                cmd.stdout.write(cmd.style.WARNING(f"Room {room.number} Reserved w/o placer"))

            if elem.placed_by != '' and not room.is_placed:
                room.is_placed = True

            room.is_available = False
        elif room.primary != '' and (not room.guest) and room.is_available:
            # Cannot unassign an already unavailable room
            room.primary = ''
            room.secondary = ''

        if elem.secondary_name != room.secondary:
            room.secondary = elem.secondary_name.title()

        old_guest = None
        old_room = None

        # Validate sp_ticket_id format if present
        if elem.ticket_id_in_secret_party and \
           not bool(sp_ticket_pattern.fullmatch(elem.ticket_id_in_secret_party)):
            cmd.stdout.write(cmd.style.ERROR(f"Skipping room {room.number} with invalid sp_ticket_id in airtable {elem.ticket_id_in_secret_party}"))
            continue

        # Always reconcile Room <-> Guest relationships when preserve mode is active
        # This ensures consistency even when sp_ticket_id hasn't changed
        ticket_changed = elem.ticket_id_in_secret_party != room.sp_ticket_id
        should_reconcile = ticket_changed or (args['preserve'] and elem.ticket_id_in_secret_party)

        if should_reconcile:
            # * we will not do anything if the existing guest has already logged in
            # * we clean up the guest association for the old guest, to allow them to be
            #   and expect it will get cleaned up by the next secret party import or
            #   by placement manually fraking with airtable
            # * if the new guest has a record with the sp_ticket_id then....
            #   * if they have an existing room already assigned, and the room has not been
            #     modified this round, we attempt to free the old room as a roombaht
            #     allocated room. if it has been modified, a warning is thrown, and system
            #     checks will probably light up, and this is why room_fix command is a thing
            #   * associate the new guest record with the current room

            # Handle ticket changes: clear old guest if ticket is different
            if ticket_changed and room.guest:
                if room.guest.last_login:
                    cmd.stdout.write(cmd.style.ERROR(f"Room{room.number} not being updated; user has already logged in!"))
                    continue

                if room.guest and elem.ticket_id_in_secret_party in [x.ticket for x in room.guest.chain(room.guest.transfer)]:
                    cmd.stdout.write(cmd.style.WARNING(f"Room {room.number} not being reconciled due to transfer {room.guest.transfer}"))
                    continue

                room.guest.room_number = None
                room.guest.hotel = None
                old_guest = room.guest
                room.guest = None

            if ticket_changed:
                # Always update sp_ticket_id when it has changed
                room.sp_ticket_id = elem.ticket_id_in_secret_party

            # Associate guest with ticket to this room
            if elem.ticket_id_in_secret_party:
                try:
                    new_guest = Guest.objects.get(ticket=elem.ticket_id_in_secret_party)


                    # Clean up guest's old room if they had one
                    if new_guest.room_number and new_guest.hotel:
                        try:
                            old_room = Room.objects.get(number=new_guest.room_number, name_hotel=new_guest.hotel)
                            if old_room.number != room.number:
                                if old_room.number in processed_rooms:
                                    cmd.stdout.write(cmd.style.WARNING(
                                        f"Not able to update {new_guest.name}'s old room {old_room.number}. "
                                        f"Please run system checks to identify potential side effects"))
                                else:
                                    old_room.guest = None
                                    old_room.primary = ""
                                    old_room.secondary = ""
                                    old_room.placed_by = ""
                                    old_room.swap_code = None
                                    old_room.placed_by_roombaht = True
                                    old_room.is_available = True
                                    old_room.is_swappable = True
                                    old_room.is_placed = False
                                    old_room.sp_ticket_id = None
                        except Room.DoesNotExist:
                            # Guest had room info but room doesn't exist - will be cleaned up
                            pass

                    # Associate guest with this room
                    new_guest.room_number = room.number
                    new_guest.hotel = room.name_hotel
                    room.guest = new_guest

                except Guest.DoesNotExist:
                    # No guest found with this ticket - clear room guest
                    if ticket_changed:
                        room.guest = None
                    else:
                        cmd.stdout.write(cmd.style.WARNING(
                            f"Room {room.number} has sp_ticket_id {elem.ticket_id_in_secret_party} "
                            f"but no matching Guest found in database"))

            # Clear room if ticket is now empty
            elif ticket_changed and not elem.ticket_id_in_secret_party:
                room.guest = None
                room.primary = ''
                room.secondary = ''
                room.placed_by = ''
                room.swap_code = None
                room.placed_by_roombaht = True
                room.is_available = True
                room.is_swappable = True
                room.is_placed = False

        # loaded room, check if room (and associated guest records) changed
        if room.is_dirty(check_relationship=True):
            if args['dry_run']:
                if old_guest and old_guest.is_dirty():
                    cmd.stdout.write(cmd.style.MIGRATE_LABEL(f"Old Guest\n{guest_changes(old_guest)}\n"))

                if room.guest and room.guest.is_dirty():
                    cmd.stdout.write(cmd.style.MIGRATE_LABEL(f"New Guest\n{guest_changes(room.guest)}\n"))

                if old_room and old_room.is_dirty(check_relationship=True):
                    cmd.stdout.write(cmd.style.MIGRATE_LABEL(f"Old Room\n{room_changes(room)}\n"))

                cmd.stdout.write(cmd.style.MIGRATE_LABEL(room_changes(room)))
            else:
                if room_update and not args['force']:
                    msg = "Proposed Changes\n"
                    if old_guest and old_guest.is_dirty():
                        msg += f"Old Guest\n{guest_changes(old_guest)}\n"

                    if room.guest and room.guest.is_dirty():
                        msg += f"New Guest\n{guest_changes(room.guest)}\n"

                    if old_room and old_room.is_dirty(check_relationship=True):
                        msg += f"Old Room\n{room_changes(old_room)}\n"

                    msg += f"{room_changes(room)} [y/n/q (to stop process)]"
                    cmd.stdout.write(cmd.style.MIGRATE_LABEL(msg))
                    a_key = getch()
                    if a_key == 'q':
                        cmd.stdout.write(cmd.style.ERROR("Giving up on update process"))
                        sys.exit(1)
                    elif a_key != 'y':
                        cmd.stdout.write(cmd.style.WARNING(f"Room {room.number} not being updated"))
                        continue

                if args['force'] and room_update:
                    room_msg = f"{'Updated' if room_update else 'Created'} {room_changes(room)}"
                else:
                    room_msg = f"{'Updated' if room_update else 'Created'} {room.name_take3} room {room.number}"

                    if room.is_swappable:
                        room_msg += ', swappable'

                    if room.is_available:
                        room_msg += ', available'

                    if room.is_placed:
                        room_msg += f", placed ({primary_name})"

                    if room.is_special:
                        room_msg += ", special!"

                # Wrap all related database writes for this room in a single transaction
                # so either all related changes commit or none do.
                try:
                    with transaction.atomic():
                        if old_guest and old_guest.is_dirty():
                            old_guest.save_dirty_fields()

                        if old_room and old_room.is_dirty(check_relationship=True):
                            old_room.save_dirty_fields()

                        if room.guest and room.guest.is_dirty():
                            room.guest.save_dirty_fields()

                        room.save_dirty_fields()
                except Exception as e:
                    # Surface the error to the user and skip further processing of this room
                    cmd.stdout.write(cmd.style.ERROR(f"Failed to save changes for room {room.number}: {e}"))
                    continue

                cmd.stdout.write(cmd.style.SUCCESS(room_msg))

            # build up some ingestion metrics
            room_count_obj = None
            if room.name_take3 not in rooms:
                room_count_obj = {
                    'count': 1,
                    'available': 0,
                    'swappable': 0
                }
            else:
                room_count_obj = rooms[room.name_take3]
                room_count_obj['count'] += 1

            if room.is_available:
                room_count_obj['available'] += 1

            if room.is_swappable:
                room_count_obj['swappable'] += 1

            rooms[room.name_take3] = room_count_obj

            processed_rooms.append(room.number)

        else:
            debug(f"No changes to room {room.number}", args)


    total_rooms = 0
    available_rooms = 0
    swappable_rooms = 0
    for r_counts, counts in rooms.items():
        cmd.stdout.write(
            f"room {r_counts} total:{counts['count']}, available:{counts['available']}"
            f", swappable:{counts['swappable']},")

        total_rooms += counts['count']
        available_rooms += counts['available']
        swappable_rooms += counts['swappable']

    placed_rooms = total_rooms - available_rooms
    cmd.stdout.write(
        f"total:{total_rooms}, available:{available_rooms}, placed:{placed_rooms}"
        f", swappable:{swappable_rooms}")

class Command(BaseCommand):
    help='Create/update rooms'

    def add_arguments(self, parser):
        parser.add_argument('rooms_file',
                            help='Path to Rooms CSV file')
        parser.add_argument('--force', '-f',
                            dest='force',
                            help='Force overwriting/updating',
                            action='store_true',
                            default=False)
        parser.add_argument('--hotel-name',
                            default="ballys",
                            help='Specify hotel name (ballys, nugget)')
        parser.add_argument('--preserve', '-p',
                            dest='preserve',
                            action='store_true',
                            default=False,
                            help='Preserve data, updating rooms in place')
        parser.add_argument('--default-check-in',
                            help='Default check in date MM/DD',
                            default=roombaht_config.DEFAULT_CHECK_IN)
        parser.add_argument('--default-check-out',
                            help='Default check out date MM/DD',
                            default=roombaht_config.DEFAULT_CHECK_OUT)
        parser.add_argument('-d', '--dry-run',
                            help='Do not actually make changes',
                            action='store_true',
                            default=False)
        parser.add_argument('--fuzziness',
                            help=f"Fuzziness confidence factor for updating name changes (default {roombaht_config.NAME_FUZZ_FACTOR})",
                            default=roombaht_config.NAME_FUZZ_FACTOR,
                            type=int)
        parser.add_argument('--skip-on-mismatch',
                            help='Skip roombot placed rooms on airtable mismatch',
                            action='store_true',
                            default=False)
        parser.add_argument('--only-room', '-o',
                            help='Only process specified rooms, may be used more than once',
                            type=str,
                            nargs='+',
                            default=[],
                            metavar='room')

    def handle(self, *args, **kwargs):
        self.verbosity = kwargs.get('verbosity', 1)
        setup_logging(self)
        if kwargs['dry_run'] and not kwargs['preserve']:
            raise CommandError('can only specify --dry-run with --preserve')

        if not kwargs['preserve']:
            if len(Room.objects.all()) > 0 or \
               len(Staff.objects.all()) > 0 or \
               len(Guest.objects.all()) > 0:
                if not kwargs['force']:
                    print('Wipe data? [y/n]')
                    if getch().lower() != 'y':
                        raise Exception('user said nope')
                else:
                    logger.info('Wiping all data at user request!')

            # Wrap deletes in a transaction to ensure the wipe is atomic.
            try:
                with transaction.atomic():
                    Room.objects.all().delete()
                    Guest.objects.all().delete()
            except Exception as e:
                raise CommandError(f"Failed to wipe existing data: {e}")
        else:
            if kwargs['dry_run']:
                self.stdout.write('Dry run for update (no changes will be made)')

        create_rooms_main(self, kwargs)
