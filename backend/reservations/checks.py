from django.core.checks import Error, Warning, Info, register
from django.core.exceptions import MultipleObjectsReturned
from reservations.models import Room, Guest


def ticket_chain(p_guest, p_chain=None):
    """Build a ticket/transfer chain for a Guest."""
    if p_chain is None:
        p_chain = []

    a_chain = [p_guest] + p_chain

    if not p_guest.transfer or p_guest.transfer == '':
        return a_chain

    try:
        a_guest = Guest.objects.get(ticket=p_guest.transfer)
    except Guest.DoesNotExist:
        return a_chain

    return ticket_chain(a_guest, a_chain)


@register(deploy=True)
def guest_drama_check(app_configs, **kwargs):
    errors = []
    guests = Guest.objects.all()


    for guest in guests:
        if guest.jwt == '' and guest.can_login:
            errors.append(Warning(f"Guest {guest.email} has an empty jwt field!",
                                  hint="Reset password via ux or user_edit",
                                  obj=guest))

        if guest.ticket and Guest.objects.filter(ticket = guest.ticket).count() > 1:
            errors.append(Error(f"Guest {guest.email}, ticket {guest.ticket} shared with other users",
                                obj=guest))

        guest_transfer_chain = ticket_chain(guest)
        chain_tail = [x for x in guest_transfer_chain if x.transfer == '']
        if len(chain_tail) == 0:
            errors.append(Error(f"Transfer chail tail not found {[x.ticket for x in guest_transfer_chain]}",
                          hint="Unable to find guest record w/o transfer in this chain." \
                                "Manually reconcile against SP exports.", obj=guest))

        for chain_guest in guest_transfer_chain:
            if chain_guest.transfer == '' \
               and chain_guest.ticket != '' \
                and chain_guest.hotel is not None \
                and chain_guest.room_number is not None:
                try:
                    chain_room = Room.objects.get(name_hotel=chain_guest.hotel, number=chain_guest.room_number)
                    if chain_room.is_placed and chain_guest.ticket != chain_room.sp_ticket_id:
                        errors.append(Warning(f"Room {chain_room.name_take3} {chain_room.number} ticket {chain_room.sp_ticket_id}" \
                                              f" does not match guest {guest.name}, ticket {guest.ticket}",
                                      hint="Manual reconciliation? Good luck, starfighter.",
                                      obj=guest))
                except Room.DoesNotExist:
                    errors.append(Warning(f"Unable to find corresponding room for {guest.email}, ticket {guest.ticket}",
                                          hint="Reimporting SP or manual reconciliation (or bug!)",
                                          obj=guest))
                except MultipleObjectsReturned:
                    errors.append(Error(f"Multiple rooms found for hotel={chain_guest.hotel}, number={chain_guest.room_number} (guest {guest.email})",
                                        hint="Database corruption - manual reconciliation required",
                                        obj=guest))

    multi_room = [','.join([str(x) for x in Guest.objects.all() if x.room_set.count() > 1])]
    if len([x for x in multi_room if len(x) > 0]) > 0:
        errors.append(Error(f"Guest records with multiple associated rooms {multi_room}"))

    # Check for tickets assigned to multiple room entries
    ticket_counts = {}
    for room in Room.objects.exclude(sp_ticket_id__isnull=True).exclude(sp_ticket_id=''):
        ticket = room.sp_ticket_id
        if ticket not in ticket_counts:
            ticket_counts[ticket] = []
        ticket_counts[ticket].append(f"{room.name_hotel} {room.number}")

    for ticket, rooms in ticket_counts.items():
        if len(rooms) > 1:
            errors.append(Error(f"Ticket {ticket} assigned to multiple rooms: {', '.join(rooms)}",
                                hint="Manually reconcile room assignments"))

    # Check for tickets assigned to multiple guest entries
    for guest in guests:
        if guest.ticket and Guest.objects.filter(ticket=guest.ticket).count() > 1:
            duplicate_guests = Guest.objects.filter(ticket=guest.ticket)
            guest_list = ', '.join([f"{g.email} (id={g.id})" for g in duplicate_guests])
            errors.append(Error(f"Ticket {guest.ticket} assigned to multiple guest entries: {guest_list}",
                                hint="Manually reconcile guest records"))

    return errors

@register(deploy=True)
def room_drama_check(app_configs, **kwargs):
    errors = []
    rooms = Room.objects.all()
    for room in rooms:
        if room.guest and room.number != room.guest.room_number:
            errors.append(Error(f"Room/guest number mismatch {room.name_hotel} {room.number} / {room.guest.email} {room.guest.hotel} {room.guest.room_number}",
                                hint='Manually reconcile room/guest numbers', obj=room))

        if room.guest and (room.primary != room.guest.name and room.guest.name not in [x.strip() for x in room.secondary.split(',')]):
            errors.append(Error(f"Room/guest name mismatch {room.name_hotel} {room.number} {room.primary} / {room.guest.name}",
                                hint='Manually reconcile room/guest names', obj=room))

        # side effect of transferring placed rooms
        if room.sp_ticket_id:
            guest = None
            alt_msg = ''
            try:
                guest = Guest.objects.get(ticket=room.sp_ticket_id)
                if room.number != guest.room_number:
                    errors.append(Error(f"Ticket {room.sp_ticket_id} room/guest number mismatch {room.number} / {guest.room_number}",
                                        hint='Manually reconcile room/guest numbers for specified ticket', obj=room))

                if room.primary != guest.name and guest.name not in [x.strip() for x in room.secondary.split(',')]:
                    errors.append(Error(f"Room {room.name_hotel} {room.number} {room.sp_ticket_id} room/guest name mismatch {room.primary} / {guest.name}",
                                        hint='Manually reconcile room/guest names for specified ticket',
                                        obj=room))

            except Guest.DoesNotExist:
                errors.append(Error(f"Original owner of {room.name_hotel} {room.number} with ticket {room.sp_ticket_id} not found",
                                    hint='Good luck, I guess?', obj=room))
            except MultipleObjectsReturned:
                errors.append(Error(f"Multiple guests found with ticket {room.sp_ticket_id} for room {room.name_hotel} {room.number}",
                                    hint='Database corruption - manual reconciliation required', obj=room))

            if room.guest is None:
                errors.append(Error(f"Room {room.number} ({room.name_hotel}) sp_ticket_id {room.sp_ticket_id} missing guest",
                                    hint='Manually reconcile w/ sources of truth', obj=room))

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
        if room.check_in is None:
            errors.append(Warning(f"Room {room.name_hotel} {room.number} has blank check_in date",
                                  hint='Fix source of truth for rooms',
                                  obj=room))

        if room.check_out is None:
            errors.append(Warning(f"Room {room.name_hotel} {room.number} has blank check_out date",
                                  hint='Fix source of truth for rooms',
                                  obj=room))


    return errors
