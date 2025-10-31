import os
import sys

from reservations.models import Room, Staff, Guest
from reservations.management import confirm

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = 'Fill empty rooms with admins. For testing only.'

    def add_arguments(self, parser):
        parser.add_argument('--max-rooms',
                            help='Maximum rooms to assign per admin. 0 is no limit.',
                            type=int,
                            default=5)
        parser.add_argument('--hotel-name',
                            default="all",
                            help='Specify hotel name (ballys, nugget, or all)')
        parser.add_argument('-d', '--dry-run',
                            help='Do not actually make changes',
                            action='store_true',
                            default=False)

    def handle(self, *args, **kwargs):
        if not settings.DEV_MODE:
            if 'staging' not in os.environ.get('ROOMBAHT_HOST', 'localhost'):
                self.stdout.write("Refusing to run in production")
                sys.exit(1)

            if not confirm("This will assign rooms to admins at random, simulating roombaht placement"):
                self.stdout.write("User said no.")
                sys.exit(1)

        free_rooms = Room.objects.filter(is_available=True)
        if kwargs['hotel_name'] != 'all':
            free_rooms = free_rooms.filter(name_hotel=kwargs['hotel_name'])

        admins = Staff.objects.all()

        assigned_rooms = {}
        for room in free_rooms:
            admin_guest = admins.order_by('?').first().guest
            if assigned_rooms.get(admin_guest.email, 0) > kwargs['max_rooms']:
                continue

            guest = Guest(name=admin_guest.name,
                          email=admin_guest.email,
                          jwt=admin_guest.jwt,
                          room_number=room.number,
                          hotel=room.name_hotel)
            guest.save()

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

            assigned_rooms[admin_guest.email] = assigned_rooms.get(admin_guest.email, 0) + 1
