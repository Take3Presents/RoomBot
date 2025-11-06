from django.core.checks import Error, Warning, Info, register, Tags
from reservations.models import Room, Guest
from django.core.exceptions import MultipleObjectsReturned
from reservations import config as roombaht_config

@register(Tags.database, deploy=True)
def guest_drama_check(app_configs, **kwargs):
    errors = []
    guests = Guest.objects.all()


    for guest in guests:
        # every guest record should be updated when jwt is changed. this check
        # should only trigger as side effect of orm manipulation
        if guest.jwt == '' and guest.can_login:
            errors.append(Warning(f"Guest {guest.email} has an empty jwt field!",
                                  hint="Have user reset password, or use user_edit",
                                  obj=guest))


        # should only occur due to orm fuckery, and potentially odd airtable intake
        if guest.ticket and Guest.objects.filter(ticket=guest.ticket).count() > 1:
            errors.append(Error(f"Guest {guest.email}, ticket {guest.ticket} shared with other users",
                                hint="If related to transfer, attempt fix_transfer_chain or manual reconciliation",
                                obj=guest))

    # Grouped check: guests imported for visible hotels should be able to login.
    # For any email group where at least one record looks like a visible-hotel single-room
    # guest, flag any records in that group that do not have can_login=True.
    emails = set(guests.values_list('email', flat=True))
    for email in emails:
        group = Guest.objects.filter(email=email)
        # if any object in the group matches the visible-hotel single-room condition
        if any(g.room_set.count() == 1 and g.hotel in roombaht_config.VISIBLE_HOTELS for g in group):
            for g in group:
                if not g.can_login:
                    errors.append(Warning(f"Guest {g.email} (id={g.id}) should be able to login!",
                                          hint="Use user_edit or update_logins to fix",
                                          obj=g))

    multi_room = [','.join([str(x) for x in Guest.objects.all() if x.room_set.count() > 1])]
    if len([x for x in multi_room if len(x) > 0]) > 0:
        errors.append(Error(f"Guest records with multiple associated rooms {multi_room}",
                            hint="Attempt manual reconciliation. Good luck, starfighter."))

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
                                hint="If related to transfer, attempt fix_transfer_chain or manual reconciliation"))

    # Check for tickets assigned to multiple guest entries
    for guest in guests:
        if guest.ticket and Guest.objects.filter(ticket=guest.ticket).count() > 1:
            duplicate_guests = Guest.objects.filter(ticket=guest.ticket)
            guest_list = ', '.join([f"{g.email} (id={g.id})" for g in duplicate_guests])
            errors.append(Error(f"Ticket {guest.ticket} assigned to multiple guest entries: {guest_list}",
                                hint="If related to transfer, attempt fix_transfer_chain or manual reconciliation"))

    return errors

@register(Tags.database, deploy=True)
def intermediate_transfer_guest_check(app_configs, **kwargs):
    """Check for intermediate guest records in transfer chains that incorrectly have rooms assigned."""
    errors = []

    # Find guests whose tickets WERE transferred to someone else
    transferred_tickets = set(Guest.objects.exclude(transfer='').exclude(transfer__isnull=True).values_list('transfer', flat=True))
    intermediate_guests = Guest.objects.filter(ticket__in=transferred_tickets)

    for guest in intermediate_guests:
        # Intermediate guests should NOT have rooms assigned
        if guest.room_number is not None:
            errors.append(Error(
                f"Intermediate transfer guest {guest.email} (ticket {guest.ticket}, was transferred to someone else) has room_number '{guest.room_number}'",
                hint="Only the final guest in a transfer chain should have a room. Check transfer processing.",
                obj=guest
            ))

        if guest.room_set.count() > 0:
            room_list = ', '.join([f"{r.name_hotel} {r.number}" for r in guest.room_set.all()])
            errors.append(Error(
                f"Intermediate transfer guest {guest.email} (ticket {guest.ticket}, was transferred to someone else) has Room objects assigned: {room_list}",
                hint="Only the final guest in a transfer chain should have associated Room. Check transfer processing.",
                obj=guest
            ))

    return errors
