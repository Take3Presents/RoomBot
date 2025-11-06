from django.core.checks import Error, Warning, register, Tags
from reservations.models import Room, Guest
from reservations.checks import room_guest_name_mismatch
from django.core.exceptions import MultipleObjectsReturned


@register(Tags.database, deploy=True)
def room_drama_check(app_configs, **kwargs):
    errors = []
    rooms = Room.objects.all()
    for room in rooms:
        # for every room, if there is a guest, make sure the number
        # on the guest record matches the actual room number
        if room.guest and room.number != room.guest.room_number:
            errors.append(Error(f"Room/guest number mismatch {room.name_hotel} {room.number} / {room.guest.email} {room.guest.hotel} {room.guest.room_number}",
                                hint='Attempt room_fix or manual reconciliation', obj=room))

        if room_guest_name_mismatch(room):
            errors.append(Error(f"Room/guest name mismatch {room.name_hotel} {room.number} {room.primary} / {room.guest.name}",
                                hint='Attempt room_fix or manual reconciliation', obj=room))

        # side effect of transferring placed rooms
        if room.sp_ticket_id:
            guest = None
            alt_msg = ''
            try:
                guest = Guest.objects.get(ticket=room.sp_ticket_id)
                if room.number != guest.room_number:
                    errors.append(Error(f"Ticket {room.sp_ticket_id} room/guest number mismatch {room.number} / {guest.room_number}",
                                        hint='Attempt room_fix or manual reconcliation', obj=room))

                if room_guest_name_mismatch(room):
                    errors.append(Error(f"Room {room.name_hotel} {room.number} {room.sp_ticket_id} room/guest name mismatch {room.primary} / {guest.name}",
                                        hint='Attempt room_fix or manual reconcliation',
                                        obj=room))

            except Guest.DoesNotExist:
                errors.append(Error(f"Original owner of {room.name_hotel} {room.number} with ticket {room.sp_ticket_id} not found",
                                    hint='Might go away on a SP import, might not. Good luck, I guess?', obj=room))
            except MultipleObjectsReturned:
                errors.append(Error(f"Multiple guests found with ticket {room.sp_ticket_id} for room {room.name_hotel} {room.number}",
                                    hint='Database corruption - manual reconciliation required', obj=room))

            if room.guest is None:
                errors.append(Error(f"Room {room.number} ({room.name_hotel}) sp_ticket_id {room.sp_ticket_id} missing guest",
                                    hint='Attempt room_fix or manual reconciliation', obj=room))

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
