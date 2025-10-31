import pytest
from unittest.mock import patch, MagicMock

from reservations.services.guest_validation_service import GuestValidationService
from reservations.models import Guest


class TestGuestValidationService:

    def setup_method(self):
        self.service = GuestValidationService()

    def test_is_valid_room_product_valid(self):
        valid_product = "04.1 Bally's - Standard 2 Queen"
        assert self.service.is_valid_room_product(valid_product) is True

    def test_is_valid_room_product_invalid(self):
        invalid_product = "Some Invalid Product"
        assert self.service.is_valid_room_product(invalid_product) is False

    @patch('reservations.services.guest_validation_service.Guest.objects.get')
    def test_is_ticket_existing_true(self, mock_get):
        mock_get.return_value = MagicMock()
        result = self.service.is_ticket_existing('EXISTING123')
        assert result is True
        mock_get.assert_called_once_with(ticket='EXISTING123')

    @patch('reservations.services.guest_validation_service.Guest.objects.get')
    def test_is_ticket_existing_false(self, mock_get):
        mock_get.side_effect = Guest.DoesNotExist()
        result = self.service.is_ticket_existing('NONEXISTENT123')
        assert result is False
        mock_get.assert_called_once_with(ticket='NONEXISTENT123')

    @patch('reservations.config.IGNORE_TRANSACTIONS', ['IGNORE1', 'IGNORE2'])
    def test_is_transaction_ignored_true(self):
        service = GuestValidationService()
        assert service.is_transaction_ignored('IGNORE1') is True

    @patch('reservations.config.IGNORE_TRANSACTIONS', ['IGNORE1', 'IGNORE2'])
    def test_is_transaction_ignored_false(self):
        service = GuestValidationService()
        assert service.is_transaction_ignored('NOT_IGNORED') is False

    def test_is_valid_hotel_true(self):
        result = self.service.is_valid_hotel("Bally's - Standard 2 Queen")
        assert result is True

    def test_is_valid_hotel_false(self):
        result = self.service.is_valid_hotel("Some Product")
        assert result is False

    def test_validate_guest_data_missing_ticket_code(self):
        guest_data = {'product': 'Some Product'}
        is_valid, reason = self.service.validate_guest_data(guest_data)
        assert is_valid is False
        assert reason == "Missing ticket code"

    def test_validate_guest_data_missing_product(self):
        guest_data = {'ticket_code': 'TEST123'}
        is_valid, reason = self.service.validate_guest_data(guest_data)
        assert is_valid is False
        assert reason == "Missing product"

    @patch('reservations.config.IGNORE_TRANSACTIONS', ['IGNORE123'])
    def test_validate_guest_data_ignored_transaction(self):
        guest_data = {
            'ticket_code': 'IGNORE123',
            'product': "Bally's - Standard 2 Queen"
        }
        service = GuestValidationService()
        is_valid, reason = service.validate_guest_data(guest_data)
        assert is_valid is False
        assert reason == "Ticket IGNORE123 is on ignore list"

    @patch('reservations.services.guest_validation_service.Guest.objects.get')
    def test_validate_guest_data_existing_ticket(self, mock_get):
        mock_get.return_value = MagicMock()
        guest_data = {
            'ticket_code': 'EXISTING123',
            'product': "Bally's - Standard 2 Queen"
        }
        is_valid, reason = self.service.validate_guest_data(guest_data)
        assert is_valid is False
        assert reason == "Ticket EXISTING123 already exists in database"

    def test_validate_guest_data_invalid_room_product(self):
        guest_data = {
            'ticket_code': 'VALID123',
            'product': 'Invalid Product'
        }
        with patch.object(self.service, 'is_ticket_existing',
                          return_value=False):
            is_valid, reason = self.service.validate_guest_data(guest_data)
            assert is_valid is False
            assert reason == "Product Invalid Product is not a valid room product"

    def test_validate_guest_data_invalid_hotel(self):
        guest_data = {
            'ticket_code': 'VALID123',
            'product': "Bally's - Standard 2 Queen"
        }
        with patch.object(self.service, 'is_ticket_existing',
                          return_value=False), \
             patch.object(self.service, 'is_valid_room_product',
                          return_value=True), \
             patch.object(self.service, 'is_valid_hotel',
                          return_value=False):

            is_valid, reason = self.service.validate_guest_data(guest_data)
            assert is_valid is False
            assert reason == "Unable to derive valid hotel for product Bally's - Standard 2 Queen"

    def test_validate_guest_data_valid(self):
        guest_data = {
            'ticket_code': 'VALID123',
            'product': "Bally's - Standard 2 Queen"
        }
        with patch.object(self.service, 'is_transaction_ignored',
                          return_value=False), \
             patch.object(self.service, 'is_ticket_existing',
                          return_value=False), \
             patch.object(self.service, 'is_valid_room_product',
                          return_value=True), \
             patch.object(self.service, 'is_valid_hotel', return_value=True):

            is_valid, reason = self.service.validate_guest_data(guest_data)
            assert is_valid is True
            assert reason is None

    def test_filter_valid_guests(self):
        guests_data = [
            {'ticket_code': 'VALID1', 'product': "Bally's - Standard 2 Queen"},
            {'ticket_code': 'INVALID1'},  # Missing product
            {'ticket_code': 'VALID2', 'product': "Bally's - Standard King"},
            {'product': "Bally's - Standard 2 Queen"},  # Missing ticket code
        ]
        with patch.object(self.service, 'validate_guest_data') as mock_validate:
            # Set up mock to return valid for VALID1 and VALID2, invalid for others
            mock_validate.side_effect = [
                (True, None),  # VALID1
                (False, "Missing product"),  # INVALID1
                (True, None),  # VALID2
                (False, "Missing ticket code"),  # Last one
            ]

            valid_guests = self.service.filter_valid_guests(guests_data)

            assert len(valid_guests) == 2
            assert valid_guests[0]['ticket_code'] == 'VALID1'
            assert valid_guests[1]['ticket_code'] == 'VALID2'

if __name__ == '__main__':
    pytest.main([__file__])
