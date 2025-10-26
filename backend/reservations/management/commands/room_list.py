from django.core.management.base import BaseCommand, CommandError
from reservations.models import Room
import reservations.config as roombaht_config

class Command(BaseCommand):
    help = "List all rooms"

    def add_arguments(self, parser):
        parser.add_argument('-t', '--room-type',
                            help='The (short) room product code')
        parser.add_argument('--hotel-name',
                            default='Ballys',
                            help='The hotel name. Defaults to Ballys.')

    def handle(self, *args, **kwargs):
        rooms = Room.objects.all()
        if kwargs['hotel_name']:
            if kwargs['hotel_name'].title() not in roombaht_config.GUEST_HOTELS:
                raise CommandError(f"Invalid hotel {kwargs['hotel_name']} specified")

            rooms = rooms.filter(name_hotel=kwargs['hotel_name'].title())

        for room in rooms:
            if kwargs['room_type'] and room.name_take3 != kwargs['room_type']:
                continue

            placed_msg = 'yes' if room.is_placed else 'no'
            special_msg = 'yes' if room.is_special else 'no'
            avail_msg = 'yes' if room.is_available else 'no'
            msg = (
                f"{room.name_hotel:10}{room.number:5}{room.hotel_sku():40} "
                f"Available: {avail_msg:4} Placed:{placed_msg:4} Special:{special_msg:4}"
            )
            self.stdout.write(msg)
