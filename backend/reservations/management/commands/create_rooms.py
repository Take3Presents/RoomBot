import sys
from fuzzywuzzy import fuzz
from django.core.management.base import BaseCommand, CommandError
from pydantic import ValidationError
from reservations.helpers import ingest_csv
from reservations.models import Room, Guest, Staff
from reservations.constants import ROOM_LIST
from reservations.ingest_models import RoomPlacementListIngest
from reservations.management import getch

def changes(room):
    msg = f"{room.name_hotel:9}{room.number:4} changes\n"
    for field, values in room.get_dirty_fields(verbose=True).items():
        saved = values['saved']
        if room.guest and field == 'primary':
            saved = f"{saved} (owner {room.guest.name})"
        msg = f"{msg}    {field} {saved} -> {values['current']}\n"

    return msg

def debug(cmd, args, msg):
    if args['debug']:
        cmd.stderr.write(msg)

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
            cmd.stderr.write(f"Validation error for row {e}")

    if len(dupe_rooms) > 0:
        raise Exception(f"Duplicate room(s) {','.join(dupe_rooms)} in CSV, refusing to process file")

    if len(dupe_tickets) > 0:
        raise Exception(f"Duplicate ticket id(s) {','.join(dupe_tickets)} in CSV, refusing to process file")

    debug(cmd, args, "read in {len(rooms_rows)} rooms for {hotel}")

    for elem in rooms_import_list:
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
            # * initial roombaht based availability
            room_name = Room.derive_room_name(hotel, elem.room_code)
            if not room_name:
                cmd.stderr.write(f"Unknown room code {elem.room_code} in {hotel} {elem.room}")
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

            if elem.placed_by_roombaht:
                room.placed_by_roombot = True
                room.is_available = True
                if room.name_hotel == 'Ballys':
                    room.is_swappable = True

        # check-in/check-out are only adjustable via room spreadsheet
        if elem.check_in_date == '' and args['default_check_in']:
            room.check_in = args['default_check_in']
        else:
            room.check_in = elem.check_in_date

        if elem.check_out_date == '' and args['default_check_out']:
            room.check_out = args['default_check_out']
        else:
            room.check_out = elem.check_out_date

        # Cannot mark a room as non available based on being set to roombaht
        #   in spreadsheet if it already actually assigned, but you can mark
        #   a room as non available/swappable if it is not assigned yet
        if (elem.placed_by == '' and not args['blank_is_available']) \
           and not room.is_special and not room.is_available:
            if not room.guest and room.is_swappable:
                room.is_swappable = False
            else:
                cmd.stderr.write(f"Not marking assigned room {room.number} as available, despite spreadsheet change")

        # the following per-guest stuff gets a bit more complex
        # TODO: Note that as we normalize names via .title() to remove chances of capitalization
        #       drama we lose the fact that some folk have mixed capitalization names i.e.
        #       Name McName and I guess we need to figure out how to handle that
        primary_name = None
        if elem.first_name_resident != '':
            primary_name = elem.first_name_resident
            if elem.last_name_resident == '':
                cmd.stderr.write(f"No last name for room {room.number}")
            else:
                primary_name = f"{primary_name} {elem.last_name_resident}"

            if room.primary != primary_name.title():
                if room.guest and room.guest.transfer:
                    trans_guest = room.guest.chain(room.guest.transfer)[-1]
                    if elem.ticket_id_in_secret_party == room.guest.ticket:
                        fuzziness = fuzz.ratio(room.primary, primary_name)
                        if fuzziness >= int(args['fuzziness']):
                            room.primary = primary_name.title()
                        else:
                            cmd.stderr.write((
                                f"Not updating primary name for room {room.number} transfer {room.guest.transfer}"
                                f" {room.primary}->{primary_name} ({fuzziness} fuzziness exceeds threshold of {args['fuzziness']}"))
                    elif trans_guest.name == primary_name.title():
                            cmd.stderr.write((
                                f"Not updating primary name for room {room.number} transfer {room.guest.transfer}"
                                f" {room.primary} -> {primary_name}"))
                    else:
                        room.primary = primary_name.title()
                else:
                    room.primary = primary_name.title()

            if elem.placed_by == '' and not args['blank_is_available']:
                cmd.stderr.write(f"Room {room.number} Reserved w/o placer")

            if elem.placed_by != '' and not room.is_placed:
                room.is_placed = True

            room.available = False
        elif room.primary != '' and (not room.guest) and room.is_available:
            # Cannot unassign an already unavailable room
            room.primary = ''
            room.secondary = ''

        if elem.secondary_name != room.secondary:
            room.secondary = elem.secondary_name.title()

        if (elem.ticket_id_in_secret_party != room.sp_ticket_id
            and elem.ticket_id_in_secret_party != 'n/a'):
            room.sp_ticket_id = elem.ticket_id_in_secret_party

	# loaded room, check if room_changed
        if room.is_dirty():
            if args['dry_run']:
                cmd.stdout.write(changes(room))
            else:
                if room_update and not args['force']:
                    msg = f"Proposed {changes(room)} [y/n/q (to stop process)]"
                    cmd.stdout.write(msg)
                    a_key = getch()
                    if a_key == 'q':
                        cmd.stderr.write("Giving up on update process")
                        sys.exit(1)
                    elif a_key != 'y':
                        cmd.stdout.write(f"Not updating {room.name_hotel} {room.number}")
                        continue

                room_msg = f"{'Updated' if room_update else 'Created'} {room.name_take3} room {room.number}"
                if room.is_swappable:
                    room_msg += ', swappable'

                if room.is_available:
                    room_msg += ', available'

                if room.is_placed:
                    room_msg += f", placed ({primary_name})"

                if room.is_special:
                    room_msg += ", special!"

                room.save_dirty_fields()
                cmd.stdout.write(room_msg)

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

        else:
            debug(cmd, args, f"No changes to room {room.number}")

    total_rooms = 0
    available_rooms = 0
    swappable_rooms = 0
    for r_counts, counts in rooms.items():
        cmd.stdout.write((
            f"room {r_counts} total:{counts['count']}, available:{counts['available']}"
            f", swappable:{counts['swappable']},"))

        total_rooms += counts['count']
        available_rooms += counts['available']
        swappable_rooms += counts['swappable']

    placed_rooms = total_rooms - available_rooms
    cmd.stdout.write((
        f"total:{total_rooms}, available:{available_rooms}, placed:{placed_rooms}"
        f", swappable:{swappable_rooms}"))

class Command(BaseCommand):
    help='Create/update rooms'

    def add_arguments(self, parser):
        parser.add_argument('rooms_file',
                            help='Path to Rooms CSV file')
        parser.add_argument('--force',
                            dest='force',
                            help='Force overwriting/updating',
                            action='store_true',
                            default=False)
        parser.add_argument('--hotel-name',
                            default="ballys",
                            help='Specify hotel name (ballys, nugget)')
        parser.add_argument('--preserve',
                            dest='preserve',
                            action='store_true',
                            default=False,
                            help='Preserve data, updating rooms in place')
        parser.add_argument('--blank-placement-is-available',
                            dest='blank_is_available',
                            action='store_true',
                            default=False,
                            help='When set it treats blank "Placed By" fields as available rooms')
        parser.add_argument('--default-check-in',
                            help='Default check in date MM/DD')
        parser.add_argument('--default-check-out',
                            help='Default check out date MM/DD')
        parser.add_argument('-d', '--dry-run',
                            help='Do not actually make changes',
                            action='store_true',
                            default=False)
        parser.add_argument('--fuzziness',
                            help='Fuzziness confidence factor for updating name changes (default 95)',
                            default='95')
        parser.add_argument('--debug',
                            help='Debug Mode. Much Debug. Wow.',
                            action='store_true',
                            default=False)

    def handle(self, *args, **kwargs):
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
                    self.stderr.write('Wiping all data at user request!')

            Room.objects.all().delete()
            Guest.objects.all().delete()
        else:
            if kwargs['dry_run']:
                self.stdout.write('Dry run for update (no changes will be made)')
            else:
                if not kwargs['force']:
                    self.stdout.write('Update (Room) data in place (experimental!) [y/n]')
                    if getch().lower() != 'y':
                        raise Exception('user said nope')

                    self.stdout.write('Updating (room) data in place at user request!')
                else:
                    self.stdout.write('Updating (room) data in place.')

        create_rooms_main(self, kwargs)
