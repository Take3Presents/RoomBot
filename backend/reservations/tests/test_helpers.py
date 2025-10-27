import datetime

import pytest


from reservations.helpers import real_date


class TestRealDate:
    def test_mm_dd_yyyy(self):
        assert real_date("11/14/2024") == datetime.date(2024, 11, 14)

    def test_mm_dd_with_two_digit_year(self):
        # 2-digit year should be interpreted as 2000 + yy
        assert real_date("1/2/24") == datetime.date(2024, 1, 2)

    def test_mm_dd_without_year_uses_provided_year(self):
        # supply year explicitly for determinism
        assert real_date("11/14", year=2023) == datetime.date(2023, 11, 14)

    def test_weekday_format_and_year_param(self):
        assert real_date("Mon 11/14", year=2025) == datetime.date(2025, 11, 14)

    def test_weekday_with_early_and_late(self):
        assert real_date("Mon 11/14 Early", year=2025) == datetime.date(2025, 11, 14)
        assert real_date("Mon 11/14 Late", year=2025) == datetime.date(2025, 11, 14)

    def test_iso_slash_year_first(self):
        assert real_date("2024/11/14") == datetime.date(2024, 11, 14)

    def test_rejects_none_and_empty_string(self):
        with pytest.raises(ValueError):
            real_date(None)
        with pytest.raises(ValueError):
            real_date("")

    def test_unparseable_raises(self):
        with pytest.raises(ValueError):
            real_date("not a date")
