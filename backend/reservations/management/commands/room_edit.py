from django.core.management.base import BaseCommand, CommandError
from reservations.models import Room
from reservations.management import getch
import reservations.config as roombaht_config

class Command(BaseCommand):
    help = "Edit aspects of a room"
    def add_arguments(self, parser):
        parser.add_argument('number',
                            help='The room number')
        parser.add_argument('--primary',
                            help='Specify primary name (blank string to remove)')
        parser.add_argument('--secondary',
                            help='Specify secondary name (blank string to remove)')

        parser.add_argument('--check-in',
                            help='Specify check-in date (MM/DD, blank string to remove)')

        parser.add_argument('--ticket',
                            help='Specify specify ticket associated with room (blank string to remove)')

        parser.add_argument('--check-out',
                            help='Specify check-out date (MM/DD, blank string to remove)')

        parser.add_argument('--hotel-name',
                            default='Ballys',
                            help='The hotel name. Defaults to Ballys.')

        # there is a better way to do this kind of arg but we cannot assume how the room is set
        parser.add_argument('--swappable',
                            help='Marks a room as swappable',
                            default=False,
                            action='store_true')

        parser.add_argument('--not-swappable',
                            help='Marks a room as not swappable',
                            default=False,
                            action='store_true')

        parser.add_argument('--placed',
                            help='Marks a room as placed',
                            default=False,
                            action='store_true')

        parser.add_argument('--not-placed',
                            help='Marks a room as not placed',
                            default=False,
                            action='store_true')

        parser.add_argument('--comp',
                            help='Marks a room as comp',
                            default=False,
                            action='store_true')

        parser.add_argument('--not-comp',
                            help='Marks a room as not comp',
                            default=False,
                            action='store_true')

        parser.add_argument('--roombaht',
                            help='Marks a room as roombaht',
                            default=False,
                            action='store_true')

        parser.add_argument('--not-roombaht',
                            help='Marks a room as not roombaht',
                            default=False,
                            action='store_true')

        parser.add_argument('--unassign',
                            help='Unassign the room. Annoying to undo',
                            default=False,
                            action='store_true')

        parser.add_argument('--reset-swap',
                            help='Resets last swap time and any pending swap code',
                            default=False,
                            action='store_true')

    def handle(self, *args, **kwargs):
        if 'number' not in kwargs:
            raise CommandError("Must specify room number")

        if kwargs['swappable'] and kwargs['not_swappable']:
            raise CommandError("Cannot specify both --swappable and --not-swappable")

        hotel = kwargs['hotel_name'].title()
        if hotel not in roombaht_config.GUEST_HOTELS:
            raise CommandError(f"Invalid hotel {kwargs['hotel_name']} specified")

        room = None
        try:
            room = Room.objects.get(number=kwargs['number'], name_hotel=hotel)
        except Room.DoesNotExist as exp:
            raise CommandError(f"Room {kwargs['number']} not found") from exp

        if kwargs['unassign']:
            if kwargs['swappable'] \
               or kwargs['not_swappable'] \
               or kwargs['primary'] \
               or kwargs['ticket'] \
               or kwargs['secondary']:
                raise CommandError('do not specify other args when unassigning room')

        if kwargs['unassign']:
            self.stdout.write((
                f"Are you sure you want to unassign {room.name_hotel} {room.number}?\n"
                f"It will be super annoying to undo this\n"
                f"[y/n]"))
            if getch().lower() != 'y':
                raise CommandError('user said nope')

            if room.guest:
                room.guest.room_number = None
                room.guest.hotel = None
                room.guest.save()
                room.guest = None

            room.primary = ''
            room.secondary = ''
            room.is_available = True
            room.is_swappable = True
            room.sp_ticket_id = ''
            room.save()
            self.stdout.write("Unassigned room")
            return

        if kwargs['primary'] is not None and kwargs['primary'] != room.primary:
            room.primary = kwargs['primary'].title()

        if kwargs['secondary'] is not None and kwargs['secondary'] != room.secondary:
            room.secondary = kwargs['secondary'].title()

        if kwargs['check_in'] is not None:
            room.check_in = kwargs['check_in']

        if kwargs['check_out'] is not None:
            room.check_out = kwargs['check_out']

        if kwargs['ticket'] is not None and kwargs['ticket'] != room.sp_ticket_id:
            room.sp_ticket_id = kwargs['ticket']

        if kwargs['swappable'] and not room.is_swappable:
            room.is_swappable = True
        elif kwargs['not_swappable'] and room.is_swappable:
            room.is_swappable = False

        if kwargs['placed'] and not room.is_placed:
            room.is_placed = True
        elif kwargs['not_placed'] and room.is_placed:
            room.is_placed = False

        if kwargs['roombaht'] and not room.placed_by_roombot:
            room.placed_by_roombot = True
        elif kwargs['not_roombaht'] and room.placed_by_roombot:
            room.placed_by_roombot = False

        if kwargs['reset_swap']:
            room.swap_time = None
            room.swap_code = None

        if room.is_dirty():
            self.stdout.write(f"Updated room: {kwargs['number']}")
            room.save_dirty_fields()
