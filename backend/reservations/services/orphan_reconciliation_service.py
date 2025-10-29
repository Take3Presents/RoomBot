import logging
from fuzzywuzzy import process, fuzz
from ..models import Guest, Room
from .transfer_chain_service import TransferChainService
from reservations.helpers import phrasing

logger = logging.getLogger(__name__)

class OrphanReconciliationService:
    def __init__(self, transfer_service=None, guest_service=None):
        """Initialize with optional dependencies for testing"""
        self.transfer_service = transfer_service or TransferChainService()
        # Only import and create guest_service if not provided (to avoid circular imports)
        if guest_service is None:
            from .guest_management_service import GuestManagementService
            self.guest_service = GuestManagementService()
        else:
            self.guest_service = guest_service

    @staticmethod
    def reconcile_orphan_rooms(guest_rows, room_counts):
        # rooms may be orphaned due to placement changes, data corruption, machine elves
        orphan_tickets = []

        def get_guest_obj(field, value):
            for guest in guest_rows:
                if field == 'name' and value == f"{guest.first_name} {guest.last_name}":
                    return guest
                if field == 'ticket' and value == guest.ticket_code:
                    return guest
            return None

        orphan_rooms = Room.objects \
                           .filter(guest=None, is_available=False) \
                           .exclude(primary='') \
                           .exclude(sp_ticket_id__exact='')

        logger.debug("Attempting to reconcile %s orphan rooms", orphan_rooms.count())

        for room in orphan_rooms:
            guest = None
            chain = []

            # first check for a guest entry by sp_ticket_id
            try:
                if room.sp_ticket_id:
                    guest = Guest.objects.get(ticket=room.sp_ticket_id)
                    logger.info("Found guest %s by sp_ticket_id in DB for orphan %s %s room %s",
                                guest.email, room.name_take3, room.name_hotel, room.number)
            except Guest.DoesNotExist:
                pass

            if not guest:
                # then check for a guest entry by room number
                try:
                    guest = Guest.objects.get(room_number=room.number, hotel=room.name_hotel)
                    logger.info("Found guest %s by room_number in DB for orphan %s %s room %s",
                                guest.email, room.name_take3, room.name_hotel, room.number)
                except Guest.DoesNotExist:
                    pass

            if guest:
                # we found one, how lovely. associate room with it.
                room.guest = guest
                if room.primary != guest.name:
                    logger.warning("names do not match for orphan room %s %s (%s, %s, %s fuzziness)",
                                   room.name_hotel, room.number, room.primary, guest.name,
                                   fuzz.ratio(room.primary, guest.name))
                    continue

                if room.primary == '':
                    room.primary = guest.name

                room_counts.orphan(room.name_take3)
                room.save()
                # Add the ticket to orphan list if it has one
                if room.sp_ticket_id:
                    orphan_tickets.append(room.sp_ticket_id)
            else:
                # then check the guest list
                guest_obj = None
                if room.sp_ticket_id is not None:
                    guest_obj = get_guest_obj('ticket', room.sp_ticket_id)

                if guest_obj:
                    logger.info("Found guest %s by ticket %s in CSV for orphan %s room %s %s",
                                guest_obj.email, room.sp_ticket_id, room.name_take3,
                                room.name_hotel, room.number)

                    # if this is a transfer, need to account for those as well
                    if guest_obj.transferred_from_code != '':
                        chain = TransferChainService.transfer_chain(guest_obj.transferred_from_code, guest_rows)
                        if len(chain) > 0:
                            for chain_guest in chain:
                                # add stubs to represent the transfers
                                # note these still get a pw given our auth model is tied to our guest model
                                stub = None
                                try:
                                    stub = Guest.objects.get(ticket=chain_guest.ticket_code)
                                    logger.debug("Found stub guest %s with ticket %s",
                                                 chain_guest.email, chain_guest.ticket_code)
                                except Guest.DoesNotExist:
                                    stub = Guest(name=f"{chain_guest.first_name} {chain_guest.last_name}".title(),
                                                 email=chain_guest.email,
                                                 ticket=chain_guest.ticket_code,
                                                 jwt=phrasing())
                                    logger.debug("Created stub guest %s with ticket %s",
                                                 chain_guest.email, chain_guest.ticket_code)

                                if chain_guest.transferred_from_code:
                                    stub.transfer = chain_guest.transferred_from_code

                                stub.save()
                                orphan_tickets.append(chain_guest.ticket_code)

                    if guest_obj:
                        # we have one, that's nice. make sure to use the same otp
                        # if we can for this guest
                        existing_guests = Guest.objects.filter(email=guest_obj.email)
                        otp = phrasing()
                        if len(existing_guests) > 0:
                            otp = existing_guests[0].jwt

                        # Import here to avoid circular imports
                        from .guest_management_service import GuestManagementService
                        GuestManagementService.update_guest(guest_obj, otp, room)
                else:
                    logger.warning("Unable to find guest %s for (non-comp) orphan room %s %s",
                                   room.primary, room.name_hotel, room.number)
                    possibilities = [x for x in process.extract(room.primary,
                                                                [f"{g.first_name} {g.last_name}" for g in guest_rows]) if x[1] > 85]
                    if len(possibilities) > 0:
                        logger.warning("Found %s fuzzy name possibilities in CSV for %s in orphan room %s %s: %s",
                                       len(possibilities), room.primary, room.name_hotel, room.number,
                                       ','.join([f"{x[0]}:{x[1]}" for x in possibilities]))
                    continue

                if room.sp_ticket_id:
                    orphan_tickets.append(room.sp_ticket_id)

        return orphan_tickets
