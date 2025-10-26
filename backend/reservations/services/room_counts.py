import logging
from ..models import Room
from reservations.constants import ROOM_LIST

logger = logging.getLogger(__name__)


class RoomCounts:
    def __init__(self):
        self.counts = {}

        for room_type in ROOM_LIST.keys():
            available_count = Room.objects.filter(
                name_take3=room_type,
                is_available=True
            ).count()

            self.counts[room_type] = {
                'available': available_count,
                'allocated': 0,
                'shortage': 0,
                'orphan': 0,
                'transfer': 0
            }

    def allocated(self, room_type: str) -> None:
        if room_type in self.counts:
            self.counts[room_type]['allocated'] += 1

    def shortage(self, room_type: str) -> None:
        if room_type in self.counts:
            self.counts[room_type]['shortage'] += 1

    def orphan(self, room_type: str) -> None:
        if room_type in self.counts:
            self.counts[room_type]['orphan'] += 1

    def transfer(self, room_type: str) -> None:
        if room_type in self.counts:
            self.counts[room_type]['transfer'] += 1

    def output(self) -> list:
        lines = []

        for room_type, counts in self.counts.items():
            hotel = ROOM_LIST[room_type].get('hotel', 'Unknown')

            remaining = Room.objects.filter(
                name_take3=room_type,
                is_available=True
            ).count()

            line = f"{hotel} - {room_type}: "
            line += f"Available: {counts['available']}, "
            line += f"Allocated: {counts['allocated']}, "
            line += f"Remaining: {remaining}"

            if counts['shortage'] > 0:
                line += f", Shortage: {counts['shortage']}"
                logger.warning(f"Room shortage detected for {room_type}: {counts['shortage']}")

            if counts['orphan'] > 0:
                line += f", Orphan: {counts['orphan']}"

            if counts['transfer'] > 0:
                line += f", Transfer: {counts['transfer']}"

            lines.append(line)
            logger.info(line)

        return lines
