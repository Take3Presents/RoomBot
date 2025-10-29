import logging
from ..models import Guest, Room
from .room_assignment_service import RoomAssignmentService
from .transfer_chain_service import TransferChainService
from .guest_management_service import GuestManagementService
from reservations.helpers import phrasing


logger = logging.getLogger(__name__)

class GuestProcessingService:
    def __init__(self):
        self.room_service = RoomAssignmentService()
        self.guest_service = GuestManagementService()

    def _handle_new_guest(self, guest_obj, room_counts):
        """
        A guest is not in the system, due to a non-placed room
        purchase or receiving a transfered room.
        """
        room = None

        logger.debug("Attempting to place new user with a %s", guest_obj.product)
        # First check if there's a placed room with matching sp_ticket_id
        try:
            placed_room = Room.objects.get(sp_ticket_id=guest_obj.ticket_code, guest=None)
            logger.info("Found placed room %s %s for new guest %s with ticket %s",
                       placed_room.name_hotel, placed_room.number, guest_obj.email, guest_obj.ticket_code)
            room = placed_room
        except Room.DoesNotExist:
            # No placed room found, find available room
            room = self.room_service.find_room(guest_obj.product)
        except Room.MultipleObjectsReturned:
            logger.error("Multiple rooms with sp_ticket_id %s found, using room assignment service",
                        guest_obj.ticket_code)
            room = self.room_service.find_room(guest_obj.product)

        if not room:
            logger.warning("No empty rooms for product %s available for %s",
                           guest_obj.product, guest_obj.email)
            room_counts.shortage(Room.short_product_code(guest_obj.product))
            return

        logger.info("Email doesnt exist: %s. Creating new guest contact.", guest_obj.email)
        otp = phrasing()
        self.guest_service.update_guest(guest_obj, otp, room)
        room_counts.allocated(room.name_take3)

    def _handle_existing_guest(self, guest_obj, guest_entries, room_counts):
        """
        Existing guests may have been manually placed, or may
        already have a room and have received a transfer.
        """
        room = self.room_service.find_room(guest_obj.product)
        logger.debug("Attempting to place existing user with a %s", guest_obj.product)
        if not room:
            logger.warning("No empty rooms for product %s available for %s",
                           guest_obj.product, guest_entries[0].email)
            room_counts.shortage(Room.short_product_code(guest_obj.product))
            return

        logger.debug("assigning room %s to (unassigned ticket/room) %s",
                     room.number, guest_entries[0].email)
        self.guest_service.update_guest(guest_obj, guest_entries[0].jwt, room)
        room_counts.allocated(room.name_take3)

    def process_guest_entries(self, guest_rows, room_counts, orphan_tickets=[]):
        transferred_tickets = []
        guests_processed = 0

        for guest_obj in guest_rows:
            if not hasattr(guest_obj, 'ticket_code'):
                logger.warning(f"Expected SecretPartyGuestIngest object, got {type(guest_obj)}")
                continue

            guest_entries = Guest.objects.filter(email=guest_obj.email)
            trans_code = guest_obj.transferred_from_code
            ticket_code = guest_obj.ticket_code

            if ticket_code in transferred_tickets:
                logger.debug("Skipping transferred ticket %s", ticket_code)
                continue

            if ticket_code in orphan_tickets:
                logger.debug("Skipping ticket %s from orphan processing", ticket_code)
                continue

            if not trans_code and guest_entries.count() == 0:
                # Unknown ticket, no transfer; new user
                self._handle_new_guest(guest_obj, room_counts)
                guests_processed += 1

            elif not trans_code and guest_entries.count() > 0:
                # There are a few cases that could pop up here
                # * admins / staff
                # * people share email addresses and soft-transfer rooms in sp
                if guest_entries.filter(ticket=ticket_code).count() == 0:
                    self._handle_existing_guest(guest_obj, guest_entries, room_counts)
                    guests_processed += 1
                else:
                    logger.warning("Not sure how to handle non-transfer, existing user ticket %s", ticket_code)

            elif trans_code:
                # Transfered ticket...
                existing_guest = None
                transfer_room = None
                chain = []

                for chain_guest in Guest.chain(trans_code):
                    if chain_guest.room_set.count() == 1:
                        existing_guest = chain_guest

                if not existing_guest:
                    # sometimes this happens due to transfers showing up earlier in the sp export than
                    # the origial ticket. so we go through the full set of rows
                    chain = TransferChainService.transfer_chain(trans_code, guest_rows)
                    if len(chain) == 0:
                        logger.warning("Ticket transfer (%s) but no previous guest found", trans_code)
                        continue

                    for idx, chain_guest in enumerate([guest_obj] + chain):
                        # add stub guests (if does not already exist)
                        # note stubs still get a jwt bc the relationship between our auth and guest model
                        stub = None
                        try:
                            stub = Guest.objects.get(ticket=chain_guest.ticket_code)
                            logger.debug("Found stub guest %s with ticket %s",
                                         chain_guest.email, chain_guest.ticket_code)
                        except Guest.DoesNotExist:
                            stub_name = f"{chain_guest.first_name} {chain_guest.last_name}".title()
                            stub = Guest(name=stub_name,
                                         email=chain_guest.email,
                                         ticket=chain_guest.ticket_code,
                                         jwt=phrasing())
                            logger.debug("Created stub guest %s with ticket %s",
                                         chain_guest.email, chain_guest.ticket_code)

                        if chain_guest.transferred_from_code:
                            stub.transfer = chain_guest.transferred_from_code

                        if idx == len(chain):
                            stub.transfer = ''

                        stub.save()
                        transferred_tickets.append(chain_guest.ticket_code)

                    # now should be able to look it up
                    existing_guest = Guest.chain(trans_code)[-1]

                # Check if existing guest has a room already
                if existing_guest.room_number is not None:
                    # Guest has existing room - process existing room transfer
                    existing_room = Room.objects.get(number=existing_guest.room_number,
                                                     name_hotel=Room.derive_hotel(guest_obj.product))

                    if guest_entries.count() == 0:
                        # Transferring to new guest...
                        logger.debug("Processing transfer of existing room %s (%s) from %s to (new guest) %s" \
                                     " %s %s - %s",
                                     trans_code, ticket_code, existing_guest.email, guest_obj.email,
                                     existing_room.name_hotel, existing_room.number, existing_room.name_take3)
                        otp = phrasing()
                        self.guest_service.update_guest(guest_obj, otp,
                                                        existing_room,
                                                        og_guest=existing_guest)
                    else:
                        # Transferring to existing guest...
                        logger.debug("Processing transfer of existing room %s (%s) from %s to %s" \
                                     " %s %s - %s",
                                     trans_code, ticket_code,
                                     existing_guest.email, guest_obj.email, existing_room.name_hotel,
                                     existing_room.number, existing_room.name_take3)
                        # i think this will result in every jwt field being the same? guest entries
                        # are kept around as part of transfers (ticket/email uniq) and when someone
                        # has multiple rooms (email/room uniq)
                        otp = guest_entries[0].jwt
                        self.guest_service.update_guest(guest_obj, otp,
                                                        existing_room, og_guest=existing_guest)

                    room_counts.allocated(existing_room.name_take3)
                    room_counts.transfer(existing_room.name_take3)
                    guests_processed += 1
                else:
                    # Guest has no room - find new room for transfer
                    transfer_room = RoomAssignmentService.find_room(guest_obj.product)
                    if not transfer_room:
                        logger.warning("No empty rooms of product %s available for %s",
                                       guest_obj.product, guest_obj.email)
                        room_counts.shortage(Room.short_product_code(guest_obj.product))
                        continue

                    email_chain = ','.join([x.email for x in chain])

                    if guest_entries.count() == 0:
                        logger.debug("Processing transfer %s (%s) from %s to (new guest) %s" \
                                     "%s %s - %s",
                                     trans_code, ticket_code, email_chain, guest_obj.email,
                                     transfer_room.name_hotel, transfer_room.number, transfer_room.name_take3)
                        otp = phrasing()
                        self.guest_service.update_guest(guest_obj, otp, transfer_room)
                    else:
                        logger.debug("Processing transfer %s (%s) from %s to %s" \
                                     "%s %s - %s",
                                     trans_code, ticket_code, email_chain, guest_obj.email,
                                     transfer_room.name_hotel, transfer_room.number, transfer_room.name_take3)
                        otp = guest_entries[0].jwt
                        self.guest_service.update_guest(guest_obj, otp, transfer_room)

                    room_counts.allocated(transfer_room.name_take3)
                    room_counts.transfer(transfer_room.name_take3)
                    guests_processed += 1

            else:
                logger.warning("Not sure how to handle ticket %s", ticket_code)

        return {
            'success': True,
            'total_processed': guests_processed
        }
