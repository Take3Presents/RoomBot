import logging
from typing import Dict, List, Set, Optional

from reservations.models import Guest, Room
from reservations import config as roombaht_config
from reservations.constants import ROOM_LIST

logger = logging.getLogger(__name__)


class GuestValidationService:

    def __init__(self):
        self._room_products = self._build_room_products_list()
        self._ignored_transactions = set(roombaht_config.IGNORE_TRANSACTIONS)
        self._guest_hotels = set(roombaht_config.GUEST_HOTELS)
        logger.debug("GuestValidationService initialized with %d room products, %d ignored transactions, %d guest hotels",
                     len(self._room_products), len(self._ignored_transactions), len(self._guest_hotels))

    def _build_room_products_list(self) -> Set[str]:
        room_products = set()
        for _take3_product, hotel_details in ROOM_LIST.items():
            for product in hotel_details.get('rooms', []):
                room_products.add(product)

        logger.debug("Built room products list with %d products", len(room_products))
        return room_products

    def is_valid_room_product(self, product: str) -> bool:
        return product in self._room_products

    def is_ticket_existing(self, ticket_code: str) -> bool:
        try:
            Guest.objects.get(ticket=ticket_code)
            return True
        except Guest.DoesNotExist:
            return False

    def is_transaction_ignored(self, ticket_code: str) -> bool:
        return ticket_code in self._ignored_transactions

    def is_valid_hotel(self, product: str) -> bool:
        try:
            hotel = Room.derive_hotel(product)
            return hotel in self._guest_hotels
        except Exception as e:
            logger.debug("Unable to derive hotel for product %s: %s", product, e)
            return False

    def validate_guest_data(self, guest_data: Dict) -> tuple[bool, Optional[str]]:
        ticket_code = guest_data.get('ticket_code')
        product = guest_data.get('product')

        if not ticket_code:
            return False, "Missing ticket code"

        if not product:
            return False, "Missing product"

        if self.is_transaction_ignored(ticket_code):
            return False, f"Ticket {ticket_code} is on ignore list"

        if self.is_ticket_existing(ticket_code):
            return False, f"Ticket {ticket_code} already exists in database"

        if not self.is_valid_room_product(product):
            return False, f"Product {product} is not a valid room product"

        if not self.is_valid_hotel(product):
            return False, f"Unable to derive valid hotel for product {product}"

        return True, None

    def filter_valid_guests(self, guests_data: List[Dict]) -> List[Dict]:
        valid_guests = []
        total_guests = len(guests_data)

        for guest_data in guests_data:
            is_valid, reason = self.validate_guest_data(guest_data)

            if is_valid:
                valid_guests.append(guest_data)
            else:
                ticket_code = guest_data.get('ticket_code', 'unknown')
                logger.debug("Skipping guest %s: %s", ticket_code, reason)

        filtered_count = len(valid_guests)
        logger.info("Filtered %d valid guests from %d total guests (%d filtered out)",
                    filtered_count, total_guests, total_guests - filtered_count)

        return valid_guests
