import logging
from fuzzywuzzy import fuzz
from ..models import Guest, Room
from reservations.config import VISIBLE_HOTELS

logger = logging.getLogger(__name__)

class GuestManagementService:

    @staticmethod
    def update_guest(guest_obj, otp, room, og_guest=None):
        ticket_code = guest_obj.ticket_code
        email = guest_obj.email
        guest = None
        guest_changed = False

        try:
            # placed rooms may already have records
            # also sometimes people transfer rooms to themselves
            # because why the frak not
            guest = Guest.objects.get(ticket=ticket_code, email=email)
            logger.debug("Found existing ticket %s for %s", ticket_code, email)

            if guest.room_number:
                if guest.room_number == room.number and room.guest == guest:
                    logger.debug("Existing guest %s already associated with room %s (%s)",
                                 email, room.number, room.name_take3)
                    return
                elif guest.room_number == room.number and room.guest is None:
                    # Guest has room_number set but room doesn't have guest - fix the association
                    logger.info("Fixing incomplete association: guest %s has room %s but room missing guest reference",
                                email, room.number)
                    # Don't return - let the code below fix room.guest
                    guest_changed = False  # Guest record is fine, just fix room
                else:
                    # transfers for placed users
                    logger.warning("Existing guest %s not moving from %s to %s (%s)",
                                   email, guest.room_number, room.number, room.name_take3)
                    return

            logger.debug("Existing guest %s assigned to %s %s (%s)",
                       email, room.number, room.name_hotel, room.name_take3)
            guest.room_number = room.number
            guest.hotel = room.name_hotel
            guest_changed = True

        except Guest.DoesNotExist:
            # but most of the time the guest does not exist yet
            guest = Guest(name=f"{guest_obj.first_name} {guest_obj.last_name}".title(),
                          ticket=guest_obj.ticket_code,
                          jwt=otp,
                          email=email,
                          room_number=room.number,
                          hotel=room.name_hotel)

            if guest_obj.transferred_from_code:
                guest.transfer = guest_obj.transferred_from_code

            logger.debug("New guest %s in %s room %s (%s)",
                         email, room.name_hotel, room.number, room.name_take3)
            guest_changed = True

        if room.name_hotel in VISIBLE_HOTELS:
            guest.can_login = True
            guest_changed = True

        # save guest (if needed) and then...
        if guest_changed:
            guest.save()

        if room.primary != '' and room.primary != guest.name:
            logger.warning("%s Room %s already has a name set: %s, guest %s!",
                           room.name_hotel, room.number, room.primary, guest.name)

        # unassociated original owner (if present)
        if room.guest and og_guest:
            if room.guest != og_guest:
                logger.warning("Unexpected original owner %s for %s room %s",
                               room.guest.email, room.name_hotel, room.number)
            room.guest.room_number = None
            room.guest.hotel = None
            logger.debug("Removing original owner %s for %s room %s",
                         room.guest.email, room.name_hotel, room.number)
            room.guest.save()

        if not room.sp_ticket_id:
            # Set sp_ticket_id if it's missing
            logger.debug("Setting room %s sp_ticket_id to %s",
                         room.number, guest.ticket)
            room.sp_ticket_id = guest.ticket
        elif room.sp_ticket_id != guest.ticket:
            # Update sp_ticket_id if it doesn't match (transfer scenario)
            logger.debug("Updating room %s sp_ticket_id %s -> %s",
                         room.number, room.sp_ticket_id, guest.ticket)
            room.sp_ticket_id = guest.ticket

        # update room
        room.guest = guest
        room.is_available = False
        room.primary = guest.name
        room.save()
