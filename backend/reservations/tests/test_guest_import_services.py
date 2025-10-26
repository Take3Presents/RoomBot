import unittest
from unittest.mock import Mock, patch
from django.test import TestCase

from reservations.services.room_counts import RoomCounts
from reservations.services.room_assignment_service import RoomAssignmentService
from reservations.services.transfer_chain_service import TransferChainService
from reservations.services.guest_management_service import GuestManagementService
from reservations.services.orphan_reconciliation_service import OrphanReconciliationService
from reservations.services.guest_processing_service import GuestProcessingService
from reservations.services.guest_ingestion_service import GuestIngestionService

from reservations.models import Guest


class TestRoomCounts(TestCase):
    @patch('reservations.services.room_counts.Room.objects')
    def setUp(self, mock_room_objects):
        mock_room_objects.filter.return_value.count.return_value = 10
        self.room_counts = RoomCounts()

    def test_initialization(self):
        self.assertIsInstance(self.room_counts.counts, dict)
        for room_type, counts in self.room_counts.counts.items():
            self.assertIn('available', counts)
            self.assertIn('allocated', counts)
            self.assertIn('shortage', counts)
            self.assertIn('orphan', counts)
            self.assertIn('transfer', counts)

    def test_counter_methods(self):
        room_type = list(self.room_counts.counts.keys())[0]  # Get first room type

        initial_shortage = self.room_counts.counts[room_type]['shortage']
        self.room_counts.shortage(room_type)
        self.assertEqual(self.room_counts.counts[room_type]['shortage'], initial_shortage + 1)

        initial_allocated = self.room_counts.counts[room_type]['allocated']
        self.room_counts.allocated(room_type)
        self.assertEqual(self.room_counts.counts[room_type]['allocated'], initial_allocated + 1)

        initial_orphan = self.room_counts.counts[room_type]['orphan']
        self.room_counts.orphan(room_type)
        self.assertEqual(self.room_counts.counts[room_type]['orphan'], initial_orphan + 1)

        initial_transfer = self.room_counts.counts[room_type]['transfer']
        self.room_counts.transfer(room_type)
        self.assertEqual(self.room_counts.counts[room_type]['transfer'], initial_transfer + 1)

    @patch('reservations.services.room_counts.Room.objects')
    @patch('reservations.services.room_counts.logger')
    def test_output_formatting(self, mock_logger, mock_room_objects):
        mock_room_objects.filter.return_value.count.return_value = 5

        room_type = list(self.room_counts.counts.keys())[0]
        self.room_counts.counts[room_type]['shortage'] = 2
        self.room_counts.counts[room_type]['allocated'] = 8
        self.room_counts.counts[room_type]['orphan'] = 1
        self.room_counts.counts[room_type]['transfer'] = 3

        output_lines = self.room_counts.output()

        self.assertIsInstance(output_lines, list)
        self.assertGreater(len(output_lines), 0)

        mock_logger.info.assert_called()
        if self.room_counts.counts[room_type]['shortage'] > 0:
            mock_logger.warning.assert_called()


class TestRoomAssignmentService(TestCase):
    def setUp(self):
        self.service = RoomAssignmentService()

    @patch('reservations.services.room_assignment_service.Room.objects')
    @patch('reservations.services.room_assignment_service.Room.short_product_code')
    @patch('reservations.services.room_assignment_service.Room.derive_hotel')
    def test_find_available_room_success(self, mock_derive_hotel, mock_short_product_code, mock_room_objects):
        mock_short_product_code.return_value = "Standard"
        mock_derive_hotel.return_value = "TestHotel"

        mock_room = Mock()
        mock_room.number = "101"
        mock_room_objects.filter.return_value.order_by.return_value.first.return_value = mock_room

        result = self.service.find_room("Standard Room Product")

        mock_room_objects.filter.assert_called_once_with(
            is_available=True,
            is_special=False,
            name_take3="Standard",
            name_hotel="TestHotel"
        )

        mock_room_objects.filter.return_value.order_by.assert_called_once_with('?')

        self.assertEqual(result, mock_room)

    @patch('reservations.services.room_assignment_service.Room.objects')
    @patch('reservations.services.room_assignment_service.Room.short_product_code')
    @patch('reservations.services.room_assignment_service.Room.derive_hotel')
    def test_find_available_room_no_rooms(self, mock_derive_hotel, mock_short_product_code, mock_room_objects):
        mock_short_product_code.return_value = "Standard"
        mock_derive_hotel.return_value = "TestHotel"
        mock_room_objects.filter.return_value.order_by.return_value.first.return_value = None

        result = self.service.find_room("Standard Room Product")

        self.assertIsNone(result)

    @patch('reservations.services.room_assignment_service.Room.short_product_code')
    def test_find_available_room_invalid_product(self, mock_short_product_code):
        mock_short_product_code.return_value = None

        with self.assertRaises(Exception) as context:
            self.service.find_room("Invalid Product")

        self.assertIn("Unknown product: Invalid Product", str(context.exception))


class TestTransferChainService(TestCase):
    def setUp(self):
        self.service = TransferChainService()

    def test_transfer_chain_simple_case(self):
        guest_obj = Mock()
        guest_obj.ticket_code = "T123"
        guest_obj.transferred_from_code = ""

        guest_rows = [guest_obj]

        result = self.service.transfer_chain("T123", guest_rows)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], guest_obj)

    def test_transfer_chain_with_transfer(self):
        guest_current = Mock()
        guest_current.ticket_code = "T123"
        guest_current.transferred_from_code = "T456"

        guest_original = Mock()
        guest_original.ticket_code = "T456"
        guest_original.transferred_from_code = ""

        guest_rows = [guest_current, guest_original]

        result = self.service.transfer_chain("T123", guest_rows)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].ticket_code, "T123")
        self.assertEqual(result[1].ticket_code, "T456")

    def test_transfer_chain_deep_chain(self):
        guest1 = Mock()
        guest1.ticket_code = "T123"
        guest1.transferred_from_code = "T456"

        guest2 = Mock()
        guest2.ticket_code = "T456"
        guest2.transferred_from_code = "T789"

        guest3 = Mock()
        guest3.ticket_code = "T789"
        guest3.transferred_from_code = ""

        guest_rows = [guest1, guest2, guest3]

        result = self.service.transfer_chain("T123", guest_rows, depth=1)

        self.assertEqual(len(result), 3)
        ticket_codes = [g.ticket_code for g in result]
        self.assertEqual(ticket_codes, ["T123", "T456", "T789"])

    def test_transfer_chain_missing_transfer(self):
        guest_current = Mock()
        guest_current.ticket_code = "T123"
        guest_current.transferred_from_code = "T999"  # Missing

        guest_rows = [guest_current]

        result = self.service.transfer_chain("T123", guest_rows)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ticket_code, "T123")


class TestGuestManagementService(TestCase):
    def setUp(self):
        self.service = GuestManagementService()

    @patch('reservations.services.guest_management_service.Guest.objects')
    def test_update_guest_new_guest(self, mock_guest_objects):
        mock_guest_objects.get.side_effect = Guest.DoesNotExist()

        guest_obj = Mock()
        guest_obj.ticket_code = "T123"
        guest_obj.email = "test@example.com"
        guest_obj.first_name = "John"
        guest_obj.last_name = "Doe"
        guest_obj.transferred_from_code = ""

        room = Mock()
        room.number = "101"
        room.name_hotel = "TestHotel"
        room.name_take3 = "Standard"
        room.primary = ""
        room.is_placed = False
        room.guest = None

        self.service.update_guest(guest_obj, "test_otp", room)

        mock_guest_objects.get.assert_called_once_with(
            ticket="T123",
            email="test@example.com"
        )

    @patch('reservations.services.guest_management_service.Guest.objects')
    def test_update_guest_existing_guest(self, mock_guest_objects):
        existing_guest = Mock()
        existing_guest.room_number = None
        existing_guest.hotel = None
        mock_guest_objects.get.return_value = existing_guest

        guest_obj = Mock()
        guest_obj.ticket_code = "T123"
        guest_obj.email = "test@example.com"
        guest_obj.first_name = "John"
        guest_obj.last_name = "Doe"

        room = Mock()
        room.number = "101"
        room.name_hotel = "TestHotel"
        room.name_take3 = "Standard"
        room.primary = ""
        room.is_placed = False
        room.guest = None

        self.service.update_guest(guest_obj, "test_otp", room)

        self.assertEqual(existing_guest.room_number, "101")
        self.assertEqual(existing_guest.hotel, "TestHotel")
        existing_guest.save.assert_called()

        self.assertEqual(room.guest, existing_guest)
        self.assertFalse(room.is_available)
        room.save.assert_called()

    @patch('reservations.services.guest_management_service.Guest.objects')
    def test_update_guest_already_assigned(self, mock_guest_objects):
        existing_guest = Mock()
        existing_guest.room_number = "101"
        mock_guest_objects.get.return_value = existing_guest

        guest_obj = Mock()
        guest_obj.ticket_code = "T123"
        guest_obj.email = "test@example.com"

        room = Mock()
        room.number = "101"

        self.service.update_guest(guest_obj, "test_otp", room)

        room.save.assert_not_called()


class TestOrphanReconciliationService(TestCase):
    def setUp(self):
        self.service = OrphanReconciliationService()

    @patch('reservations.services.orphan_reconciliation_service.Room.objects')
    @patch('reservations.services.orphan_reconciliation_service.Guest.objects')
    def test_reconcile_orphan_rooms_with_sp_ticket_id(self, mock_guest_objects, mock_room_objects):
        room_counts = Mock()

        orphan_room = Mock()
        orphan_room.sp_ticket_id = "T123"
        orphan_room.number = "101"
        orphan_room.name_hotel = "TestHotel"
        orphan_room.name_take3 = "Standard"
        orphan_room.primary = "John Doe"

        mock_queryset = Mock()
        mock_queryset.count.return_value = 1
        mock_queryset.__iter__ = Mock(return_value=iter([orphan_room]))
        mock_room_objects.filter.return_value.exclude.return_value.exclude.return_value = mock_queryset

        existing_guest = Mock()
        existing_guest.email = "john@example.com"
        existing_guest.name = "John Doe"
        mock_guest_objects.get.return_value = existing_guest

        guest_rows = []
        result = self.service.reconcile_orphan_rooms(guest_rows, room_counts)
        mock_guest_objects.get.assert_called_with(ticket="T123")
        room_counts.orphan.assert_called_with("Standard")
        self.assertIn("T123", result)

    @patch('reservations.services.orphan_reconciliation_service.Room.objects')
    @patch('reservations.services.orphan_reconciliation_service.Guest.objects')
    @patch('reservations.services.orphan_reconciliation_service.process')
    def test_reconcile_orphan_rooms_fuzzy_matching(self, mock_process, mock_guest_objects, mock_room_objects):
        room_counts = Mock()

        orphan_room = Mock()
        orphan_room.sp_ticket_id = None
        orphan_room.number = "101"
        orphan_room.name_hotel = "TestHotel"
        orphan_room.name_take3 = "Standard"
        orphan_room.primary = "Jon Doe"  # Slightly different name

        mock_queryset = Mock()
        mock_queryset.count.return_value = 1
        mock_queryset.__iter__ = Mock(return_value=iter([orphan_room]))
        mock_room_objects.filter.return_value.exclude.return_value.exclude.return_value = mock_queryset

        mock_guest_objects.get.side_effect = Guest.DoesNotExist()
        guest_rows = [Mock()]
        guest_rows[0].first_name = "John"
        guest_rows[0].last_name = "Doe"
        guest_rows[0].email = "john@example.com"

        mock_process.extract.return_value = [("John Doe", 90)]  # Above 85% threshold

        result = self.service.reconcile_orphan_rooms(guest_rows, room_counts)

        mock_process.extract.assert_called()
        self.assertIsInstance(result, list)

    @patch('reservations.services.orphan_reconciliation_service.Room.objects')
    @patch('reservations.services.orphan_reconciliation_service.Guest.objects')
    def test_reconcile_orphan_rooms_empty_case(self, mock_guest_objects, mock_room_objects):
        room_counts = Mock()

        mock_queryset = Mock()
        mock_queryset.count.return_value = 0
        mock_queryset.__iter__ = Mock(return_value=iter([]))
        mock_room_objects.filter.return_value.exclude.return_value.exclude.return_value = mock_queryset

        guest_rows = []

        result = self.service.reconcile_orphan_rooms(guest_rows, room_counts)

        self.assertEqual(result, [])


class TestGuestProcessingService(TestCase):
    def setUp(self):
        self.service = GuestProcessingService()

    @patch('reservations.services.guest_processing_service.Guest.objects')
    def test_handle_new_guest(self, mock_guest_objects):
        mock_guest_objects.filter.return_value.count.return_value = 0

        with patch.object(self.service.room_service, 'find_room') as mock_find_room:
            mock_room = Mock()
            mock_room.name_take3 = "Standard"
            mock_find_room.return_value = mock_room

            with patch.object(self.service.guest_service, 'update_guest') as mock_update_guest:
                room_counts = Mock()

                guest_obj = Mock()
                guest_obj.product = "Standard Room"
                guest_obj.email = "new@example.com"

                self.service._handle_new_guest(guest_obj, room_counts)

                mock_find_room.assert_called_once_with("Standard Room")
                mock_update_guest.assert_called_once()
                room_counts.allocated.assert_called_once_with("Standard")

    @patch('reservations.services.guest_processing_service.Guest.objects')
    def test_handle_new_guest_no_room(self, mock_guest_objects):
        with patch.object(self.service.room_service, 'find_room', return_value=None):
            with patch('reservations.services.guest_processing_service.Room.short_product_code') as mock_short_code:
                mock_short_code.return_value = "Standard"

                room_counts = Mock()
                guest_obj = Mock()
                guest_obj.product = "Standard Room"
                guest_obj.email = "new@example.com"

                self.service._handle_new_guest(guest_obj, room_counts)

                room_counts.shortage.assert_called_once_with("Standard")

    @patch('reservations.services.guest_processing_service.Guest.objects')
    def test_process_guest_entries_orchestration(self, mock_guest_objects):
        room_counts = Mock()
        orphan_tickets = ["T999"]
        guest_obj = Mock()
        guest_obj.email = "test@example.com"
        guest_obj.ticket_code = "T123"
        guest_obj.transferred_from_code = ""

        guest_rows = [guest_obj]

        mock_guest_objects.filter.return_value.count.return_value = 0

        with patch.object(self.service, '_handle_new_guest') as mock_handle_new:
            self.service.process_guest_entries(guest_rows, room_counts, orphan_tickets)
            mock_handle_new.assert_called_once_with(guest_obj, room_counts)

    def test_process_guest_entries_skips_orphan_tickets(self):
        room_counts = Mock()
        orphan_tickets = ["T123"]  # This ticket should be skipped

        guest_obj = Mock()
        guest_obj.ticket_code = "T123"
        guest_obj.email = "test@example.com"

        guest_rows = [guest_obj]

        with patch.object(self.service, '_handle_new_guest') as mock_handle_new:
            self.service.process_guest_entries(guest_rows, room_counts, orphan_tickets)
            mock_handle_new.assert_not_called()

    @patch('reservations.services.guest_processing_service.Guest.objects')
    def test_handle_existing_guest(self, mock_guest_objects):
        existing_guest = Mock()
        existing_guest.jwt = "existing_jwt"
        guest_entries = Mock()
        guest_entries.filter.return_value.count.return_value = 0
        guest_entries.__getitem__ = Mock(return_value=existing_guest)

        with patch.object(self.service.room_service, 'find_room') as mock_find_room:
            mock_room = Mock()
            mock_room.name_take3 = "Standard"
            mock_find_room.return_value = mock_room

            with patch.object(self.service.guest_service, 'update_guest') as mock_update_guest:
                room_counts = Mock()
                guest_obj = Mock()
                guest_obj.product = "Standard Room"

                self.service._handle_existing_guest(guest_obj, guest_entries, room_counts)
                mock_update_guest.assert_called_once()
                room_counts.allocated.assert_called_once()


class TestGuestIngestionService(TestCase):
    def setUp(self):
        self.service = GuestIngestionService()

    @patch('reservations.secret_party.SecretPartyClient')
    @patch('reservations.config.SP_API_KEY', 'test_key')
    def test_fetch_from_secretparty(self, mock_client_class):
        mock_client = Mock()
        mock_client.export_tickets.return_value = [
            {'id': 'T123', 'email': 'test@example.com'},
            {'id': 'T456', 'email': 'test2@example.com'}
        ]
        mock_client_class.return_value = mock_client

        result = self.service._fetch_from_secretparty()

        mock_client_class.assert_called_once_with('test_key')
        mock_client.export_tickets.assert_called_once_with(
            search=[{"label": "type: add-on"}],
            reverse=True,
            order='purchase_date'
        )

        self.assertIn('tickets', result)
        self.assertIn('metadata', result)
        self.assertEqual(len(result['tickets']), 2)
        self.assertEqual(result['metadata']['total_records'], 2)

    @patch('reservations.helpers.ingest_csv')
    @patch('pathlib.Path.exists')
    def test_fetch_from_csv_clean_data(self, mock_path_exists, mock_ingest_csv):
        mock_path_exists.return_value = True

        mock_fields = ['name', 'email', 'product']
        mock_guests = [
            {'name': 'John Doe', 'email': 'john@example.com', 'product': 'Standard Room'},
            {'name': 'Jane Smith', 'email': 'jane@example.com', 'product': 'Deluxe Room'}
        ]
        mock_ingest_csv.return_value = (mock_fields, mock_guests)
        config = {'file_path': '/test/guests.csv'}
        result = self.service._fetch_from_csv(config)
        mock_ingest_csv.assert_called_once_with('/test/guests.csv')

        self.assertIn('guests', result)
        self.assertIn('fields', result)
        self.assertIn('metadata', result)
        self.assertEqual(len(result['guests']), 2)
        self.assertEqual(result['fields'], mock_fields)
        self.assertEqual(result['metadata']['total_records'], 2)
        self.assertEqual(result['metadata']['fields_found'], mock_fields)

    @patch('reservations.helpers.ingest_csv')
    @patch('pathlib.Path.exists')
    def test_fetch_from_csv_file_not_found(self, mock_path_exists, mock_ingest_csv):
        config = {'file_path': '/test/nonexistent.csv'}
        mock_path_exists.return_value = False
        with self.assertRaises(ValueError) as context:
            self.service._fetch_from_csv(config)

        self.assertIn("CSV file not found", str(context.exception))
        mock_ingest_csv.assert_not_called()

    @patch.object(GuestIngestionService, '_fetch_from_secretparty')
    @patch.object(GuestIngestionService, '_transform_external_data')
    @patch.object(GuestIngestionService, '_process_ingestion_data')
    def test_ingest_from_external_source_secretparty(self, mock_process, mock_transform, mock_fetch):
        mock_raw_data = {'tickets': [{'id': 'T123'}]}
        mock_transformed_data = {'guests': [Mock()]}
        mock_results = {'success': True, 'total_processed': 1}

        mock_fetch.return_value = mock_raw_data
        mock_transform.return_value = mock_transformed_data
        mock_process.return_value = mock_results

        result = self.service.ingest_from_external_source('secretparty')

        mock_fetch.assert_called_once()
        mock_transform.assert_called_once_with(mock_raw_data, 'secretparty')
        mock_process.assert_called_once_with(mock_transformed_data)

        self.assertEqual(result['source'], 'secretparty')
        self.assertIn('ingestion_timestamp', result)
        self.assertEqual(result['success'], True)

    @patch.object(GuestIngestionService, '_fetch_from_csv')
    @patch.object(GuestIngestionService, '_transform_external_data')
    @patch.object(GuestIngestionService, '_process_ingestion_data')
    def test_ingest_from_external_source_csv(self, mock_process, mock_transform, mock_fetch):
        config = {'file_path': '/test/guests.csv'}
        mock_raw_data = {'guests': [{'name': 'Test', 'email': 'test@example.com'}]}
        mock_transformed_data = {'guests': [Mock()]}
        mock_results = {'success': True, 'total_processed': 1}

        mock_fetch.return_value = mock_raw_data
        mock_transform.return_value = mock_transformed_data
        mock_process.return_value = mock_results

        result = self.service.ingest_from_external_source('csv', config)

        mock_fetch.assert_called_once_with(config)
        mock_transform.assert_called_once_with(mock_raw_data, 'csv')
        mock_process.assert_called_once_with(mock_transformed_data)

        self.assertEqual(result['source'], 'csv')
        self.assertIn('ingestion_timestamp', result)

    @patch('reservations.ingest_models.SecretPartyGuestIngest')
    def test_transform_csv_data(self, mock_guest_ingest):
        mock_guest_obj1 = Mock()
        mock_guest_obj2 = Mock()
        mock_guest_ingest.from_source.side_effect = [mock_guest_obj1, mock_guest_obj2]

        raw_data = {
            'guests': [
                {'name': 'John Doe', 'email': 'john@example.com'},
                {'name': 'Jane Smith', 'email': 'jane@example.com'}
            ]
        }

        result = self.service._transform_csv_data(raw_data)

        self.assertEqual(mock_guest_ingest.from_source.call_count, 2)
        mock_guest_ingest.from_source.assert_any_call(
            {'name': 'John Doe', 'email': 'john@example.com'}, 'csv'
        )
        mock_guest_ingest.from_source.assert_any_call(
            {'name': 'Jane Smith', 'email': 'jane@example.com'}, 'csv'
        )

        self.assertIn('guests', result)
        self.assertEqual(len(result['guests']), 2)
        self.assertIn(mock_guest_obj1, result['guests'])
        self.assertIn(mock_guest_obj2, result['guests'])

    @patch.object(GuestIngestionService, '_fetch_from_source')
    def test_ingest_from_external_source_error_handling(self, mock_fetch):
        mock_fetch.side_effect = Exception("API connection failed")

        result = self.service.ingest_from_external_source('secretparty')

        self.assertEqual(result['success'], False)
        self.assertIn('API connection failed', result['error'])
        self.assertEqual(result['source'], 'secretparty')
        self.assertIn('ingestion_timestamp', result)


if __name__ == '__main__':
    unittest.main()
