from django.core.management.base import BaseCommand, CommandError
from fuzzywuzzy import fuzz
from reservations.models import Room, Guest
from reservations.checks import room_guest_name_mismatch
from reservations.management import getch
import reservations.config as roombaht_config

class Command(BaseCommand):
    help = "Fixes corrupted room records and associations"
    def add_arguments(self, parser):
        parser.add_argument('number',
                            help='The room number')
        parser.add_argument('--hotel-name',
                            default='Ballys',
                            help='The hotel name. Defaults to Ballys.')
        parser.add_argument('--fuzziness',
                            help=f"Fuzziness confidence factor for updating name changes (default {roombaht_config.NAME_FUZZ_FACTOR})",
                            default=roombaht_config.NAME_FUZZ_FACTOR,
                            type=int)

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

        if (room.guest and room_guest_name_mismatch(room)) or (not room.guest):
            if room.guest:
                self.stdout.write(f"Guest {room.guest.name} not found in room occupants")
            else:
                self.stdout.write("No guest associated with this room")

            occupants = room.occupants()
            matched_any = False

            max_fuzz = 0
            base_name = room.guest.name if room.guest else ''
            # First try to fuzz match as before
            for name in occupants:
                fuzziness = fuzz.ratio(base_name, name)
                if fuzziness >= kwargs['fuzziness']:
                    matched_any = True
                    # Only update existing guest records if we have an original guest to base them on
                    if room.guest:
                        guest_entries = Guest.objects.filter(email=room.guest.email)
                        self.stdout.write(self.style.SUCCESS(f"Updating guest {guest_entries.count()} record(s) with {fuzziness} fuzzy match {name}"))
                        for guest in guest_entries:
                            guest.name = name
                            guest.save()

                if fuzziness > max_fuzz:
                    max_fuzz = fuzziness

            if matched_any:
                return

            # No fuzzy matches: present a numbered list and a quit option
            self.stdout.write(f"No fuzzy matches found (max {max_fuzz}). Please select the correct occupant to associate with this room:")

            # Build options: show occupants, and include the currently associated guest as an option if not present
            options = []  # list of (display, real_name)
            for name in occupants:
                options.append((name, name))

            associated_name = room.guest.name if hasattr(room, 'guest') and room.guest else None
            if associated_name and associated_name not in occupants:
                associated_ticket = getattr(room.guest, 'ticket', None)
                if not associated_ticket:
                    # fallback to the room's sp_ticket_id if guest.ticket is not set
                    associated_ticket = room.sp_ticket_id
                if associated_ticket:
                    display = f"{associated_name} (associated, ticket {associated_ticket})"
                else:
                    display = f"{associated_name} (associated)"
                options.append((display, associated_name))

            for idx, (display, _) in enumerate(options, start=1):
                self.stdout.write(f"{idx}. {display}")
            self.stdout.write("q. Quit")

            self.stdout.write("Select occupant number or 'q' to quit")
            choice = getch()
            if choice.lower() == 'q':
                self.stdout.write("Aborting room fix")
                return

            try:
                sel_idx = int(choice) - 1
                if sel_idx < 0 or sel_idx >= len(options):
                    raise ValueError()
            except ValueError:
                raise CommandError("Invalid selection")

            selected_name = options[sel_idx][1]

            # Attempt to find an existing guest record per rules
            og_guest = room.guest
            guest = None

            if room.sp_ticket_id:
                candidates = Guest.objects.filter(ticket=room.sp_ticket_id)
            else:
                candidates = Guest.objects.filter(name__iexact=selected_name)

            # prefer candidates in this order
            # * if the sp ticket id matches
            # * if there is no ticket, room number, or hotel
            preferred = None
            for c in candidates:
                if room.sp_ticket_id and c.ticket == room.sp_ticket_id:
                    preferred = c
                    break
                elif not c.ticket or not c.room_number or not c.hotel:
                    preferred = c
                    break

            if preferred:
                guest = preferred
                guest.name = selected_name
                guest.room_number = room.number
                guest.hotel = room.name_hotel
                if room.name_hotel in roombaht_config.VISIBLE_HOTELS:
                    guest.can_login = True

                guest.save()
                self.stdout.write(self.style.SUCCESS(f"Associated existing guest {guest.email or '[no email]'} ({guest.name}) with room {room.number}"))
            else:
                # Create a new guest record if we couldn't find a suitable candidate
                email = og_guest.email if og_guest and hasattr(og_guest, 'email') else ''
                ticket = room.sp_ticket_id or ''
                # If we have any candidates, use their jwt for continuity; otherwise jwt will be empty if not available
                jwt_val = candidates[0].jwt if candidates else ''
                guest = Guest(name=selected_name,
                              email=email,
                              ticket=ticket,
                              jwt=jwt_val,
                              room_number=room.number,
                              hotel=room.name_hotel)
                if room.name_hotel in roombaht_config.VISIBLE_HOTELS:
                    guest.can_login = True
                guest.save()
                self.stdout.write(self.style.SUCCESS(f"Created new guest {guest.email or '[no email]'} ({guest.name}) and associated with room {room.number}"))

            # If there was an original guest, disassociate if different
            if og_guest and og_guest != guest:
                og_guest.room_number = None
                og_guest.hotel = None
                og_guest.save()

            # Update room and sp_ticket_id as needed
            if not room.sp_ticket_id:
                room.sp_ticket_id = guest.ticket
            elif room.sp_ticket_id != guest.ticket:
                room.sp_ticket_id = guest.ticket

            room.guest = guest
            room.is_available = False
            room.primary = guest.name
            room.save()
