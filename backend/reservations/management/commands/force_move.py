from django.core.management.base import BaseCommand, CommandError
from reservations.models import Room, ForceMoveError

class Command(BaseCommand):
    help = "Manually force move a room"
    def add_arguments(self, parser):
        parser.add_argument('src_room',
                            help='The source room guests will be moved from')
        parser.add_argument('dest_room',
                            help='The destination room guests will be moved to')
        parser.add_argument('--hotel_one',
                            help='The hotel the source room is associated with. Defaults to Ballys.',
                            default='Ballys')
        parser.add_argument('--hotel_two',
                            help='The hotel the destination room is associated with. Defaults to Ballys.',
                            default='Ballys')

    def handle(self, *args, **kwargs):
        if 'src_room' not in kwargs or 'dest_room' not in kwargs:
            raise CommandError('must specify src_room and dest_room')

        src_room = None
        dest_room = None

        try:
            src_room = Room.objects.get(number=kwargs['src_room'], name_hotel=kwargs['hotel_one'])
        except Room.DoesNotExist:
            raise CommandError(f"room {kwargs['hotel_one']} {kwargs['src_room']} does not exist") from Room.DoesNotExist

        try:
            dest_room = Room.objects.get(number=kwargs['dest_room'], name_hotel=kwargs['hotel_two'])
        except Room.DoesNotExist:
            raise CommandError(f"room {kwargs['hotel_two']} {kwargs['dest_room']} does not exist") from Room.DoesNotExist

        if not src_room.swappable():
            raise CommandError(f"room {kwargs['hotel_one']} {kwargs['src_room']} is not swappable")

        # This is a force move, so the target room does not need to be swappable

        try:
            Room.force_move(src_room, dest_room)
        except ForceMoveError as exp:
            raise CommandError(f"Unable to force move room {exp.msg}") from exp

        self.stdout.write(f"Moved guests from {kwargs['hotel_one']} {kwargs['src_room']} to {kwargs['hotel_two']} {kwargs['dest_room']}")
