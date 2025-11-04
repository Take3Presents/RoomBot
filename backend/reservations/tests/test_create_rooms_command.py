"""
Unit tests for create_rooms.py management command.

These tests exercise the actual create_rooms_main function with real data,
using Django's TestCase for database isolation and minimal mocking.
"""
import csv
import os
import tempfile
from io import StringIO
from unittest.mock import patch, Mock

from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError

from reservations.models import Room, Guest
from reservations.management.commands.create_rooms import Command, create_rooms_main


class CreateRoomsTestBase(TestCase):
    """Base test class with utility methods for creating test CSV files"""

    def create_csv_file(self, rows, hotel='ballys'):
        """Create a temporary CSV file with the given rows

        Automatically fixes room codes if they don't match the expected format
        """
        # Fix room codes if needed
        for row in rows:
            room_code = row.get('Room Code', '')
            if room_code and '-' not in room_code:
                # Convert short codes like 'BLSD' to proper format like 'ballys-SD'
                # SD = Standard Double (2Q code), K = King, etc.
                if hotel == 'ballys':
                    if room_code in ['BLSD', 'SD']:
                        row['Room Code'] = 'ballys-2Q'  # Standard 2 Queen
                    elif room_code == 'K':
                        row['Room Code'] = 'ballys-K'  # King
                    elif room_code == 'INVALID':
                        row['Room Code'] = 'ballys-INVALID'  # Keep invalid for testing
                elif hotel == 'nugget':
                    if room_code in ['QQS', 'SD']:
                        row['Room Code'] = 'gnlt-QQS'  # Standard Double Queen
                    elif room_code == 'KS':
                        row['Room Code'] = 'gnlt-KS'  # King

        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv')
        writer = csv.DictWriter(temp_file, fieldnames=[
            'Placement Verified',
            'Room',
            'Room Type',
            'Room Features (Accessibility, Lakeview, Smoking)',
            'First Name (Resident)',
            'Last Name (Resident)',
            'Secondary Name',
            'Check-In Date',
            'Check-Out Date',
            'Placed By',
            'Placed By Roombaht',
            'Ticket ID in SecretParty',
            'Room Code'
        ])
        writer.writeheader()
        writer.writerows(rows)
        temp_file.close()
        return temp_file.name

    def tearDown(self):
        """Clean up any temporary files"""
        # TestCase will handle database cleanup automatically


class TestCSVIngestionAndValidation(CreateRoomsTestBase):
    """Test CSV parsing and validation logic"""

    def test_valid_csv_creates_rooms(self):
        """Test that a valid CSV file successfully creates rooms"""
        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': '',
                'Last Name (Resident)': '',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': '',
                'Placed By Roombaht': 'TRUE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            },
            {
                'Placement Verified': 'Yes',
                'Room': '501',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': '',
                'Last Name (Resident)': '',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': '',
                'Placed By Roombaht': 'TRUE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()
            args = {
                'rooms_file': csv_file,
                'hotel_name': 'ballys',
                'force': True,
                'preserve': False,
                'default_check_in': '11/14',
                'default_check_out': '11/17',
                'dry_run': False,
                'fuzziness': 80,
                'skip_on_mismatch': False,
                'only_room': [],
                'verbosity': 1
            }

            create_rooms_main(cmd, args)

            # Verify rooms were created
            self.assertEqual(Room.objects.count(), 2)
            room_500 = Room.objects.get(number=500)
            self.assertEqual(room_500.name_hotel, 'Ballys')
            self.assertTrue(room_500.is_available)
            self.assertTrue(room_500.placed_by_roombot)
        finally:
            os.unlink(csv_file)

    def test_duplicate_room_numbers_raises_exception(self):
        """Test that duplicate room numbers in CSV raise an exception"""
        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': '',
                'Last Name (Resident)': '',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': '',
                'Placed By Roombaht': 'TRUE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            },
            {
                'Placement Verified': 'Yes',
                'Room': '500',  # Duplicate!
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': '',
                'Last Name (Resident)': '',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': '',
                'Placed By Roombaht': 'TRUE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()
            args = {
                'rooms_file': csv_file,
                'hotel_name': 'ballys',
                'force': True,
                'preserve': False,
                'default_check_in': '11/14',
                'default_check_out': '11/17',
                'dry_run': False,
                'fuzziness': 80,
                'skip_on_mismatch': False,
                'only_room': [],
                'verbosity': 1
            }

            with self.assertRaises(Exception) as context:
                create_rooms_main(cmd, args)

            self.assertIn("Duplicate room(s)", str(context.exception))
            self.assertIn("500", str(context.exception))
        finally:
            os.unlink(csv_file)

    def test_duplicate_sp_ticket_ids_raises_exception(self):
        """Test that duplicate SP ticket IDs in CSV raise an exception"""
        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': 'John',
                'Last Name (Resident)': 'Doe',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': 'Staff',
                'Placed By Roombaht': 'FALSE',
                'Ticket ID in SecretParty': 'ABC123',
                'Room Code': 'SD'
            },
            {
                'Placement Verified': 'Yes',
                'Room': '501',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': 'Jane',
                'Last Name (Resident)': 'Smith',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': 'Staff',
                'Placed By Roombaht': 'FALSE',
                'Ticket ID in SecretParty': 'ABC123',  # Duplicate!
                'Room Code': 'SD'
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()
            args = {
                'rooms_file': csv_file,
                'hotel_name': 'ballys',
                'force': True,
                'preserve': False,
                'default_check_in': '11/14',
                'default_check_out': '11/17',
                'dry_run': False,
                'fuzziness': 80,
                'skip_on_mismatch': False,
                'only_room': [],
                'verbosity': 1
            }

            with self.assertRaises(Exception) as context:
                create_rooms_main(cmd, args)

            self.assertIn("Duplicate ticket id(s)", str(context.exception))
            self.assertIn("ABC123", str(context.exception))
        finally:
            os.unlink(csv_file)

    def test_invalid_sp_ticket_pattern_skips_room(self):
        """Test that invalid SP ticket ID patterns are skipped with error"""
        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': 'John',
                'Last Name (Resident)': 'Doe',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': 'Staff',
                'Placed By Roombaht': 'FALSE',
                'Ticket ID in SecretParty': 'INVALID!',  # Invalid pattern
                'Room Code': 'BLSD'
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()
            args = {
                'rooms_file': csv_file,
                'hotel_name': 'ballys',
                'force': True,
                'preserve': False,
                'default_check_in': '11/14',
                'default_check_out': '11/17',
                'dry_run': False,
                'fuzziness': 80,
                'skip_on_mismatch': False,
                'only_room': [],
                'verbosity': 1
            }

            create_rooms_main(cmd, args)

            # Room should not have been created due to invalid ticket
            self.assertEqual(Room.objects.count(), 0)
            output = cmd.stdout.getvalue()
            self.assertIn("invalid sp_ticket_id", output.lower())
        finally:
            os.unlink(csv_file)

    def test_invalid_room_code_skips_room(self):
        """Test that invalid room codes are skipped with error"""
        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Unknown Type',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': '',
                'Last Name (Resident)': '',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': '',
                'Placed By Roombaht': 'TRUE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'INVALID'  # Invalid room code
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()
            args = {
                'rooms_file': csv_file,
                'hotel_name': 'ballys',
                'force': True,
                'preserve': False,
                'default_check_in': '11/14',
                'default_check_out': '11/17',
                'dry_run': False,
                'fuzziness': 80,
                'skip_on_mismatch': False,
                'only_room': [],
                'verbosity': 1
            }

            create_rooms_main(cmd, args)

            # Room should not have been created
            self.assertEqual(Room.objects.count(), 0)
            output = cmd.stdout.getvalue()
            self.assertIn("Unknown room code", output)
        finally:
            os.unlink(csv_file)


class TestRoomFeatures(CreateRoomsTestBase):
    """Test room feature detection and assignment"""

    def test_ada_feature_detection(self):
        """Test that ADA features are properly detected and set"""
        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': 'ADA',
                'First Name (Resident)': '',
                'Last Name (Resident)': '',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': '',
                'Placed By Roombaht': 'TRUE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()
            args = {
                'rooms_file': csv_file,
                'hotel_name': 'ballys',
                'force': True,
                'preserve': False,
                'default_check_in': '11/14',
                'default_check_out': '11/17',
                'dry_run': False,
                'fuzziness': 80,
                'skip_on_mismatch': False,
                'only_room': [],
                'verbosity': 1
            }

            create_rooms_main(cmd, args)

            room = Room.objects.get(number=500)
            self.assertTrue(room.is_ada)
        finally:
            os.unlink(csv_file)

    def test_hearing_accessible_feature_detection(self):
        """Test that hearing accessible features are properly detected"""
        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': 'Hearing Accessible',
                'First Name (Resident)': '',
                'Last Name (Resident)': '',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': '',
                'Placed By Roombaht': 'TRUE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()
            args = {
                'rooms_file': csv_file,
                'hotel_name': 'ballys',
                'force': True,
                'preserve': False,
                'default_check_in': '11/14',
                'default_check_out': '11/17',
                'dry_run': False,
                'fuzziness': 80,
                'skip_on_mismatch': False,
                'only_room': [],
                'verbosity': 1
            }

            create_rooms_main(cmd, args)

            room = Room.objects.get(number=500)
            self.assertTrue(room.is_hearing_accessible)
        finally:
            os.unlink(csv_file)

    def test_lakeview_feature_detection(self):
        """Test that lakeview features are properly detected"""
        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': 'Lakeview',
                'First Name (Resident)': '',
                'Last Name (Resident)': '',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': '',
                'Placed By Roombaht': 'TRUE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()
            args = {
                'rooms_file': csv_file,
                'hotel_name': 'ballys',
                'force': True,
                'preserve': False,
                'default_check_in': '11/14',
                'default_check_out': '11/17',
                'dry_run': False,
                'fuzziness': 80,
                'skip_on_mismatch': False,
                'only_room': [],
                'verbosity': 1
            }

            create_rooms_main(cmd, args)

            room = Room.objects.get(number=500)
            self.assertTrue(room.is_lakeview)
        finally:
            os.unlink(csv_file)


class TestRoomPlacement(CreateRoomsTestBase):
    """Test room placement logic and status flags"""

    def test_room_marked_as_placed_when_assigned(self):
        """Test that rooms are marked as placed when they have a resident"""
        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': 'John',
                'Last Name (Resident)': 'Doe',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': 'Staff',
                'Placed By Roombaht': 'FALSE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()
            args = {
                'rooms_file': csv_file,
                'hotel_name': 'ballys',
                'force': True,
                'preserve': False,
                'default_check_in': '11/14',
                'default_check_out': '11/17',
                'dry_run': False,
                'fuzziness': 80,
                'skip_on_mismatch': False,
                'only_room': [],
                'verbosity': 1
            }

            create_rooms_main(cmd, args)

            room = Room.objects.get(number=500)
            self.assertTrue(room.is_placed)
            self.assertFalse(room.is_available)
            self.assertEqual(room.primary, 'John Doe')
        finally:
            os.unlink(csv_file)

    def test_roombot_placed_room_flags(self):
        """Test that roombot-placed rooms have correct flags"""
        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': '',
                'Last Name (Resident)': '',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': '',
                'Placed By Roombaht': 'TRUE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()
            args = {
                'rooms_file': csv_file,
                'hotel_name': 'ballys',
                'force': True,
                'preserve': False,
                'default_check_in': '11/14',
                'default_check_out': '11/17',
                'dry_run': False,
                'fuzziness': 80,
                'skip_on_mismatch': False,
                'only_room': [],
                'verbosity': 1
            }

            create_rooms_main(cmd, args)

            room = Room.objects.get(number=500)
            self.assertTrue(room.placed_by_roombot)
            self.assertTrue(room.is_available)
            self.assertTrue(room.is_swappable)
            self.assertFalse(room.is_placed)
        finally:
            os.unlink(csv_file)


class TestGuestAssignment(CreateRoomsTestBase):
    """Test guest-room association logic"""

    def test_guest_reassignment_on_sp_ticket_change(self):
        """Test that guests are properly reassigned when sp_ticket_id changes on existing room

        The guest assignment logic in create_rooms triggers when a room's sp_ticket_id
        CHANGES. This test creates an existing room with a guest, then updates it with
        a different sp_ticket_id to verify the reassignment logic works.
        """
        # Create the first guest and room
        old_guest = Guest.objects.create(
            ticket='OLD123',
            email='old@example.com',
            name='Old Guest',
            jwt='old_jwt_token'
        )

        room = Room.objects.create(
            number=500,
            name_hotel='Ballys',
            name_take3='Queen',
            guest=old_guest,
            sp_ticket_id='OLD123',
            primary='Old Guest',
            is_placed=True,
            is_available=False
        )

        old_guest.room_number = 500
        old_guest.hotel = 'Ballys'
        old_guest.save()

        # Create the new guest to assign
        new_guest = Guest.objects.create(
            ticket='ABC123',
            email='john@example.com',
            name='John Doe',
            jwt='new_jwt_token'
        )

        # Now update the room with a different sp_ticket_id
        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': 'John',
                'Last Name (Resident)': 'Doe',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': 'Staff',
                'Placed By Roombaht': 'FALSE',
                'Ticket ID in SecretParty': 'ABC123',  # Changed from OLD123
                'Room Code': 'BLSD'
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()
            args = {
                'rooms_file': csv_file,
                'hotel_name': 'ballys',
                'force': True,
                'preserve': True,  # Use preserve mode to update existing room
                'default_check_in': '11/14',
                'default_check_out': '11/17',
                'dry_run': False,
                'fuzziness': 80,
                'skip_on_mismatch': False,
                'only_room': [],
                'verbosity': 1
            }

            create_rooms_main(cmd, args)

            # Reload objects from database
            room.refresh_from_db()
            old_guest.refresh_from_db()
            new_guest.refresh_from_db()

            # Verify the guest reassignment worked
            self.assertEqual(room.guest, new_guest)
            self.assertEqual(room.sp_ticket_id, 'ABC123')
            # room_number is a CharField, so it's stored as a string
            self.assertEqual(new_guest.room_number, '500')
            self.assertEqual(new_guest.hotel, 'Ballys')

            # Old guest should be unassigned
            self.assertIsNone(old_guest.room_number)
            self.assertIsNone(old_guest.hotel)
        finally:
            os.unlink(csv_file)


class TestNameHandling(CreateRoomsTestBase):
    """Test name normalization and fuzzy matching"""

    def test_primary_name_from_first_and_last(self):
        """Test that primary name is constructed from first and last names"""
        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': 'john',
                'Last Name (Resident)': 'doe',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': 'Staff',
                'Placed By Roombaht': 'FALSE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()
            args = {
                'rooms_file': csv_file,
                'hotel_name': 'ballys',
                'force': True,
                'preserve': False,
                'default_check_in': '11/14',
                'default_check_out': '11/17',
                'dry_run': False,
                'fuzziness': 80,
                'skip_on_mismatch': False,
                'only_room': [],
                'verbosity': 1
            }

            create_rooms_main(cmd, args)

            room = Room.objects.get(number=500)
            # Names should be title-cased
            self.assertEqual(room.primary, 'John Doe')
        finally:
            os.unlink(csv_file)

    def test_secondary_name_update(self):
        """Test that secondary names are properly set"""
        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': 'John',
                'Last Name (Resident)': 'Doe',
                'Secondary Name': 'Jane Smith',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': 'Staff',
                'Placed By Roombaht': 'FALSE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()
            args = {
                'rooms_file': csv_file,
                'hotel_name': 'ballys',
                'force': True,
                'preserve': False,
                'default_check_in': '11/14',
                'default_check_out': '11/17',
                'dry_run': False,
                'fuzziness': 80,
                'skip_on_mismatch': False,
                'only_room': [],
                'verbosity': 1
            }

            create_rooms_main(cmd, args)

            room = Room.objects.get(number=500)
            self.assertEqual(room.secondary, 'Jane Smith')
        finally:
            os.unlink(csv_file)


class TestOnlyRoomFilter(CreateRoomsTestBase):
    """Test the --only-room filtering functionality"""

    def test_only_room_filters_correctly(self):
        """Test that --only-room processes only specified rooms"""
        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': '',
                'Last Name (Resident)': '',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': '',
                'Placed By Roombaht': 'TRUE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            },
            {
                'Placement Verified': 'Yes',
                'Room': '501',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': '',
                'Last Name (Resident)': '',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': '',
                'Placed By Roombaht': 'TRUE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()
            args = {
                'rooms_file': csv_file,
                'hotel_name': 'ballys',
                'force': True,
                'preserve': False,
                'default_check_in': '11/14',
                'default_check_out': '11/17',
                'dry_run': False,
                'fuzziness': 80,
                'skip_on_mismatch': False,
                'only_room': ['500'],  # Only process room 500
                'verbosity': 1
            }

            create_rooms_main(cmd, args)

            # Only room 500 should exist
            self.assertEqual(Room.objects.count(), 1)
            self.assertTrue(Room.objects.filter(number=500).exists())
            self.assertFalse(Room.objects.filter(number=501).exists())
        finally:
            os.unlink(csv_file)


class TestDryRunMode(CreateRoomsTestBase):
    """Test --dry-run functionality"""

    def test_dry_run_requires_preserve(self):
        """Test that --dry-run requires --preserve flag"""
        csv_file = self.create_csv_file([])

        try:
            cmd = Command()
            cmd.stdout = StringIO()

            with self.assertRaises(CommandError) as context:
                cmd.handle(
                    rooms_file=csv_file,
                    hotel_name='ballys',
                    force=False,
                    preserve=False,
                    default_check_in='11/14',
                    default_check_out='11/17',
                    dry_run=True,
                    fuzziness=80,
                    skip_on_mismatch=False,
                    only_room=[],
                    verbosity=1
                )

            self.assertIn("can only specify --dry-run with --preserve", str(context.exception))
        finally:
            os.unlink(csv_file)


class TestDataWipeConfirmation(CreateRoomsTestBase):
    """Test data wipe confirmation logic"""

    @patch('reservations.management.commands.create_rooms.getch')
    def test_wipe_confirmation_on_existing_data(self, mock_getch):
        """Test that existing data triggers wipe confirmation"""
        # Create some existing data
        Room.objects.create(
            number=100,
            name_hotel='Ballys',
            name_take3='Standard Double'
        )

        mock_getch.return_value = 'y'

        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': '',
                'Last Name (Resident)': '',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': '',
                'Placed By Roombaht': 'TRUE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()

            cmd.handle(
                rooms_file=csv_file,
                hotel_name='ballys',
                force=False,
                preserve=False,
                default_check_in='11/14',
                default_check_out='11/17',
                dry_run=False,
                fuzziness=80,
                skip_on_mismatch=False,
                only_room=[],
                verbosity=1
            )

            # Old room should be wiped, new room created
            self.assertFalse(Room.objects.filter(number=100).exists())
            self.assertTrue(Room.objects.filter(number=500).exists())
        finally:
            os.unlink(csv_file)

    def test_force_skips_wipe_confirmation(self):
        """Test that --force flag skips wipe confirmation"""
        # Create some existing data
        Room.objects.create(
            number=100,
            name_hotel='Ballys',
            name_take3='Standard Double'
        )

        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': '',
                'Last Name (Resident)': '',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': '',
                'Placed By Roombaht': 'TRUE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()

            cmd.handle(
                rooms_file=csv_file,
                hotel_name='ballys',
                force=True,  # Should skip confirmation
                preserve=False,
                default_check_in='11/14',
                default_check_out='11/17',
                dry_run=False,
                fuzziness=80,
                skip_on_mismatch=False,
                only_room=[],
                verbosity=1
            )

            # Old room wiped, new room created (no getch call needed)
            self.assertFalse(Room.objects.filter(number=100).exists())
            self.assertTrue(Room.objects.filter(number=500).exists())
        finally:
            os.unlink(csv_file)


class TestRoomMetrics(CreateRoomsTestBase):
    """Test room count and metrics output"""

    def test_room_metrics_output(self):
        """Test that room metrics are correctly calculated and output"""
        csv_file = self.create_csv_file([
            {
                'Placement Verified': 'Yes',
                'Room': '500',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': '',
                'Last Name (Resident)': '',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': '',
                'Placed By Roombaht': 'TRUE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            },
            {
                'Placement Verified': 'Yes',
                'Room': '501',
                'Room Type': 'Standard Double',
                'Room Features (Accessibility, Lakeview, Smoking)': '',
                'First Name (Resident)': 'John',
                'Last Name (Resident)': 'Doe',
                'Secondary Name': '',
                'Check-In Date': '11/14',
                'Check-Out Date': '11/17',
                'Placed By': 'Staff',
                'Placed By Roombaht': 'FALSE',
                'Ticket ID in SecretParty': '',
                'Room Code': 'BLSD'
            }
        ])

        try:
            cmd = Command()
            cmd.stdout = StringIO()
            args = {
                'rooms_file': csv_file,
                'hotel_name': 'ballys',
                'force': True,
                'preserve': False,
                'default_check_in': '11/14',
                'default_check_out': '11/17',
                'dry_run': False,
                'fuzziness': 80,
                'skip_on_mismatch': False,
                'only_room': [],
                'verbosity': 1
            }

            create_rooms_main(cmd, args)

            output = cmd.stdout.getvalue()
            # Should contain metrics about total, available, placed
            self.assertIn('total:', output)
            self.assertIn('available:', output)
            self.assertIn('placed:', output)
            self.assertIn('swappable:', output)
        finally:
            os.unlink(csv_file)
