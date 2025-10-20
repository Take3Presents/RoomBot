import sys

from reservations.models import Room, Staff

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = 'Fill empty rooms with admins. For testing only.'

    def add_arguments(self, parser):
        parser.add_argument('--max-rooms',
                            help='Maximum rooms to assign per admin. 0 is no limit.',
                            default=5)
        parser.add_argument('--hotel-name',
                            default="all",
                            help='Specify hotel name (ballys, nugget, or all)')
        parser.add_argument('-d', '--dry-run',
                            help='Do not actually make changes',
                            action='store_true',
                            default=False)

    def handle(self, *args, **kwargs):
        # todo once we are happy with this script, replace "refuse" with
        # "seek enthusiastic consent from user"
        if not settings.DEV_MODE:
            self.stdout.write("Refusing to run outside of dev mode")
            sys.exit(1)

        free_rooms = Room.objects.filter(is_available=True)
        if kwargs['hotel_name'] != 'all':
            free_rooms = free_rooms.filter(name_hotel=kwargs['hotel'])

        admins = Staff.objects.all()

        for room in free_rooms:
            guest = admins.order_by('?').first().guest
            room.guest = guest
            room.is_available = False
            room.primary = guest.name
            room.swappable = True

            msg = f"{guest.name} to {room.name_hotel} {room.number}"
            if kwargs['dry_run']:
                self.stdout.write(f"Would have assigned {msg}")
            else:
                room.save()
                self.stdout.write(f"Assigned {msg}")
