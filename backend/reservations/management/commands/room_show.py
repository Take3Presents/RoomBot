from django.core.management.base import BaseCommand, CommandError
from django.utils.timezone import localtime
from reservations.models import Room, Swap
import reservations.config as roombaht_config

class Command(BaseCommand):
    help = "Show information on a room"
    def add_arguments(self, parser):
        parser.add_argument('number',
                            help='The room number')
        parser.add_argument('--hotel-name',
                            default='Ballys',
                            help='The hotel name. Defaults to Ballys.')

    def handle(self, *args, **kwargs):
        if 'number' not in kwargs:
            raise CommandError("Must specify room number")

        room = None
        hotel = kwargs['hotel_name'].title()
        if hotel not in roombaht_config.GUEST_HOTELS:
            raise CommandError(f"Invalid hotel {kwargs['hotel_name']} specified")

        try:
            room = Room.objects.get(number=kwargs['number'], name_hotel=hotel)
        except Room.DoesNotExist as exp:
            raise CommandError(f"Room {kwargs['number']} not found in {kwargs['hotel_name']}") from exp

        desc = f"{room.hotel_sku()} in {room.name_hotel}"
        if room.guest:
            desc = f"{desc} owned by {room.guest.email}"

        if room.primary:
            desc = f"{desc}\n   primary resident: {room.primary}"
            if room.secondary:
                desc = f"{desc}, secondary resident: {room.secondary}"

        flags = []
        if room.is_available:
            flags.append('available')

        if room.swappable():
            flags.append('swappable')

        if room.is_placed:
            flags.append('placed')

        if room.placed_by_roombot:
            flags.append('roombaht')

        if room.is_special:
            flags.append('special')

        details = ''
        if len(flags) > 0:
            details = f"{details} Flags: {','.join(flags)}"

        if room.check_in:
            details = f"{details} Check-in: {room.check_in}"
        else:
            details = f"{details} Check-in: Unknown"

        if room.check_out:
            details = f"{details} Check-out: {room.check_out}"
        else:
            details = f"{details} Check-out: Unknown"

        details += f" SP ticket: {room.sp_ticket_id if room.sp_ticket_id else 'n/a'}"

        self.stdout.write(desc)
        self.stdout.write(details)

        if room.swap_code:
            self.stdout.write("Room swap is pending. ")

        if room.swap_time:
            self.stdout.write(f"Room last swapped {room.swap_time.strftime('%H:%M%p %Z on %b %d, %Y')}")

        # Include any logged Swap records involving this room (both directions)
        swaps = list(Swap.objects.filter(room_one=room)) + list(Swap.objects.filter(room_two=room))
        if swaps:
            # sort by creation time
            swaps.sort(key=lambda s: s.created_at)
            self.stdout.write('\nSwaps involving this room:')
            for s in swaps:
                t = localtime(s.created_at).strftime('%H:%M%p %Z on %b %d, %Y')
                rooms_str = f"{s.room_one} <-> {s.room_two}"
                # guest_one was originally in room_one and moved to room_two; guest_two vice-versa
                direction = f"{s.guest_one.name} -> {s.room_two} ; {s.guest_two.name} -> {s.room_one}"
                self.stdout.write(f"{t}: {rooms_str} | {direction}")
