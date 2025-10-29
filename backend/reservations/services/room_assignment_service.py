import logging
from ..models import Room

logger = logging.getLogger(__name__)

class RoomAssignmentService:
    @staticmethod
    def find_room(room_product):
        room_type = Room.short_product_code(room_product)
        hotel = Room.derive_hotel(room_product)

        if not room_type:
            raise Exception("Unable to actually find room type for %s" % room_product)

        # We only auto-assign rooms if these criteria are met
        # * must be available
        # * must not be art - we should (if ever) rarely see these as art rooms
        #                     should always placed
        # * must not be special room (i.e. unknown to roombaht)
        available_room = Room.objects \
            .filter(is_available=True,
                    is_special=False,
                    name_take3=room_type,
                    name_hotel=hotel) \
            .order_by('?') \
            .first()

        if not available_room:
            logger.debug("No room of type %s available in %s. Product: %s",
                         room_type, hotel, room_product)
        else:
            logger.debug("Found free room of type %s in %s: %s",
                         room_type, hotel, available_room.number)

        return available_room
