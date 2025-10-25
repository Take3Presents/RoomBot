from csv import DictReader
import os

from django.conf import settings
import pytest

from reservations.models import RoomClass


@pytest.mark.django_db
class TestRoomClass:
    def get_csv_fixture_path(self, filename: str) -> str:
        return os.path.join(settings.BASE_DIR, "reservations", "fixtures", filename)

    def count_unique_room_code__sp_asset_name_combos(self, filename: str) -> int:
        room_code__sp_asset_name_set = set()

        with open(filename, "r") as f:
            reader = DictReader(f)
            RoomClass.objects._normalize_fieldnames(reader)
            for row in reader:
                sp_asset_names = row["sp_asset_names"].strip().split("\n")
                for sp_asset_name in sp_asset_names:
                    room_code__sp_asset_name_set.add((row["hotel_room_type_code"], sp_asset_name))

        return len(room_code__sp_asset_name_set)

    def test_bulk_create_from_csv_rs25_nugget_heavenly_tower(self):
        filename = self.get_csv_fixture_path("RS25 - Golden Nugget - Heavenly Tower Key.csv")
        RoomClass.objects.bulk_create_from_csv(filename)
        assert RoomClass.objects.count() == 16
        assert RoomClass.objects.count() == self.count_unique_room_code__sp_asset_name_combos(filename)

    def test_bulk_create_from_csv_rs25_nugget_sunset_tower(self):
        filename = self.get_csv_fixture_path("RS25 - Golden Nugget - Sunset Tower Key.csv")
        RoomClass.objects.bulk_create_from_csv(filename)
        assert RoomClass.objects.count() == 16
        assert RoomClass.objects.count() == self.count_unique_room_code__sp_asset_name_combos(filename)

    def test_bulk_create_from_csv_rs25_ballys_full_tower(self):
        filename = self.get_csv_fixture_path("RS25 - Bally's - Full Tower Key.csv")
        RoomClass.objects.bulk_create_from_csv(filename)

        # There are three floor groupings:
        #
        #   - Floors {3, 4, 5, 6, 7, 8, 9, 10}
        #   - Floor {11}
        #   - Floors {12, 15, 16, 17}

        # There are 9 unique suite room codes with 2 asset names each. The
        # asset names for the suites are the same regardless of which floor
        # grouping they appear on.
        unique_suite_room_code__sp_asset_name_combos = 9 * 2  # 18

        # There are 16 unique non-suite room codes with 2 asset names each
        # _per floor grouping_.
        unique_non_suite_room_code__sp_asset_name_combos = 16 * 2 * 3  # 96

        assert RoomClass.objects.count() == (
            unique_suite_room_code__sp_asset_name_combos +
            unique_non_suite_room_code__sp_asset_name_combos
        )  # 114
        assert RoomClass.objects.count() == self.count_unique_room_code__sp_asset_name_combos(filename)

    def test_bulk_create_from_csv_rs25_all_hotels_and_wings(self):
        unique_room_code__sp_asset_name_combos_count = 0

        for filename in (
            "RS25 - Golden Nugget - Heavenly Tower Key.csv",
            "RS25 - Golden Nugget - Sunset Tower Key.csv",
            "RS25 - Bally's - Full Tower Key.csv"
        ):
            full_path = self.get_csv_fixture_path(filename)
            RoomClass.objects.bulk_create_from_csv(full_path)
            unique_room_code__sp_asset_name_combos_count += self.count_unique_room_code__sp_asset_name_combos(full_path)

        assert RoomClass.objects.count() == unique_room_code__sp_asset_name_combos_count
        assert RoomClass.objects.filter(hotel_name=RoomClass.HotelName.BALLYS).count() == 114
        assert RoomClass.objects.filter(hotel_name=RoomClass.HotelName.NUGGET).count() == 32
