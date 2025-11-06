from io import StringIO
from unittest.mock import Mock, patch
from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError

from reservations.models import Room, Guest
from reservations.management.commands.room_edit import Command


class TestRoomEditCommand(TestCase):
    """Test suite for the room_edit management command"""

    def setUp(self):
        """Set up test fixtures"""
        # Create a test guest
        self.test_guest = Guest.objects.create(
            name="Test User",
            email="test@example.com",
            ticket="T123",
            transfer="",
            invitation="",
            jwt="test_jwt",
            room_number="500",
            hotel="Ballys",
            can_login=True
        )

        # Create a test room
        self.test_room = Room.objects.create(
            number="500",
            name_take3="King",
            name_hotel="Ballys",
            is_available=False,
            is_swappable=True,
            is_placed=False,
            primary="Test User",
            secondary="",
            sp_ticket_id="T123",
            guest=self.test_guest,
            placed_by_roombot=False
        )

    def call_command(self, *args, **kwargs):
        """Helper to call command and capture output"""
        out = StringIO()
        err = StringIO()
        call_command('room_edit', *args, stdout=out, stderr=err, **kwargs)
        return out.getvalue(), err.getvalue()

    def test_edit_primary_name(self):
        """Test updating primary contact name"""
        out, err = self.call_command('500', '--primary=John Smith', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertEqual(self.test_room.primary, "John Smith")
        self.assertIn("Updated room: 500", out)

    def test_edit_secondary_name(self):
        """Test updating secondary contact name"""
        out, err = self.call_command('500', '--secondary=Jane Doe', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertEqual(self.test_room.secondary, "Jane Doe")
        self.assertIn("Updated room: 500", out)

    def test_clear_primary_name(self):
        """Test clearing primary contact name with blank string"""
        out, err = self.call_command('500', '--primary=', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertEqual(self.test_room.primary, "")

    def test_clear_secondary_name(self):
        """Test clearing secondary contact name with blank string"""
        self.test_room.secondary = "Jane Doe"
        self.test_room.save()

        out, err = self.call_command('500', '--secondary=', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertEqual(self.test_room.secondary, "")

    def test_edit_ticket_id(self):
        """Test updating ticket ID"""
        out, err = self.call_command('500', '--ticket=T999', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertEqual(self.test_room.sp_ticket_id, "T999")

    def test_clear_ticket_id(self):
        """Test clearing ticket ID with blank string"""
        out, err = self.call_command('500', '--ticket=', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertEqual(self.test_room.sp_ticket_id, "")

    def test_edit_check_in_date(self):
        """Test updating check-in date"""
        out, err = self.call_command('500', '--check-in=12/25', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertIsNotNone(self.test_room.check_in)
        self.assertEqual(self.test_room.check_in.month, 12)
        self.assertEqual(self.test_room.check_in.day, 25)

    def test_edit_check_out_date(self):
        """Test updating check-out date"""
        out, err = self.call_command('500', '--check-out=12/30', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertIsNotNone(self.test_room.check_out)
        self.assertEqual(self.test_room.check_out.month, 12)
        self.assertEqual(self.test_room.check_out.day, 30)

    def test_clear_check_in_date(self):
        """Test clearing check-in date"""
        from datetime import date
        self.test_room.check_in = date(2024, 12, 25)
        self.test_room.save()

        out, err = self.call_command('500', '--check-in=', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertIsNone(self.test_room.check_in)

    def test_clear_check_out_date(self):
        """Test clearing check-out date"""
        from datetime import date
        self.test_room.check_out = date(2024, 12, 30)
        self.test_room.save()

        out, err = self.call_command('500', '--check-out=', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertIsNone(self.test_room.check_out)

    def test_mark_swappable(self):
        """Test marking room as swappable"""
        self.test_room.is_swappable = False
        self.test_room.save()

        out, err = self.call_command('500', '--swappable', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertTrue(self.test_room.is_swappable)

    def test_mark_not_swappable(self):
        """Test marking room as not swappable"""
        out, err = self.call_command('500', '--not-swappable', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertFalse(self.test_room.is_swappable)

    def test_mark_placed(self):
        """Test marking room as placed"""
        out, err = self.call_command('500', '--placed', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertTrue(self.test_room.is_placed)

    def test_mark_not_placed(self):
        """Test marking room as not placed"""
        self.test_room.is_placed = True
        self.test_room.save()

        out, err = self.call_command('500', '--not-placed', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertFalse(self.test_room.is_placed)

    def test_mark_roombaht(self):
        """Test marking room as placed by roombot"""
        out, err = self.call_command('500', '--roombaht', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertTrue(self.test_room.placed_by_roombot)

    def test_mark_not_roombaht(self):
        """Test marking room as not placed by roombot"""
        self.test_room.placed_by_roombot = True
        self.test_room.save()

        out, err = self.call_command('500', '--not-roombaht', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertFalse(self.test_room.placed_by_roombot)

    def test_reset_swap(self):
        """Test resetting swap time and code"""
        from datetime import datetime
        from django.utils.timezone import make_aware

        self.test_room.swap_time = make_aware(datetime.utcnow())
        self.test_room.swap_code = "TESTCODE123"
        self.test_room.save()

        out, err = self.call_command('500', '--reset-swap', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.assertIsNone(self.test_room.swap_time)
        self.assertIsNone(self.test_room.swap_code)

    @patch('reservations.management.commands.room_edit.getch')
    def test_unassign_room_confirmed(self, mock_getch):
        """Test unassigning a room with confirmation"""
        mock_getch.return_value = 'y'

        out, err = self.call_command('500', '--unassign', '--hotel-name=Ballys')

        self.test_room.refresh_from_db()
        self.test_guest.refresh_from_db()

        self.assertEqual(self.test_room.primary, '')
        self.assertEqual(self.test_room.secondary, '')
        self.assertEqual(self.test_room.sp_ticket_id, '')
        self.assertTrue(self.test_room.is_available)
        self.assertTrue(self.test_room.is_swappable)
        self.assertIsNone(self.test_room.guest)

        self.assertIsNone(self.test_guest.room_number)
        self.assertIsNone(self.test_guest.hotel)

        self.assertIn("Unassigned room", out)

    @patch('reservations.management.commands.room_edit.getch')
    def test_unassign_room_cancelled(self, mock_getch):
        """Test unassigning a room when user cancels"""
        mock_getch.return_value = 'n'

        with self.assertRaises(CommandError) as context:
            self.call_command('500', '--unassign', '--hotel-name=Ballys')

        self.assertIn("user said nope", str(context.exception))

        # Room should be unchanged
        self.test_room.refresh_from_db()
        self.assertEqual(self.test_room.guest, self.test_guest)

    def test_unassign_with_other_args_fails(self):
        """Test that unassign fails when combined with other arguments"""
        with self.assertRaises(CommandError) as context:
            self.call_command('500', '--unassign', '--swappable', '--hotel-name=Ballys')

        self.assertIn("do not specify other args when unassigning room", str(context.exception))

    def test_conflicting_swappable_flags(self):
        """Test that conflicting swappable flags raise an error"""
        with self.assertRaises(CommandError) as context:
            self.call_command('500', '--swappable', '--not-swappable', '--hotel-name=Ballys')

        self.assertIn("Cannot specify both --swappable and --not-swappable", str(context.exception))

    def test_room_not_found(self):
        """Test error when room doesn't exist"""
        with self.assertRaises(CommandError) as context:
            self.call_command('999', '--hotel-name=Ballys')

        self.assertIn("Room 999 not found", str(context.exception))

    def test_invalid_hotel(self):
        """Test error with invalid hotel name"""
        with self.assertRaises(CommandError) as context:
            self.call_command('500', '--hotel-name=InvalidHotel')

        self.assertIn("Invalid hotel InvalidHotel specified", str(context.exception))

    def test_hotel_name_case_insensitive(self):
        """Test that hotel name is case-insensitive"""
        out, err = self.call_command('500', '--primary=Test Name', '--hotel-name=ballys')

        self.test_room.refresh_from_db()
        self.assertEqual(self.test_room.primary, "Test Name")

    def test_no_changes_no_update_message(self):
        """Test that no update message appears when no changes made"""
        # Call command with current values (no actual changes)
        out, err = self.call_command('500', '--hotel-name=Ballys')

        # Should not contain "Updated room" since nothing changed
        self.assertNotIn("Updated room", out)

    def test_multiple_edits_at_once(self):
        """Test making multiple edits in a single command"""
        out, err = self.call_command(
            '500',
            '--primary=New Primary',
            '--secondary=New Secondary',
            '--ticket=T555',
            '--swappable',
            '--placed',
            '--hotel-name=Ballys'
        )

        self.test_room.refresh_from_db()
        self.assertEqual(self.test_room.primary, "New Primary")
        self.assertEqual(self.test_room.secondary, "New Secondary")
        self.assertEqual(self.test_room.sp_ticket_id, "T555")
        self.assertTrue(self.test_room.is_swappable)
        self.assertTrue(self.test_room.is_placed)

    def test_edit_nugget_room(self):
        """Test editing a Nugget hotel room"""
        nugget_guest = Guest.objects.create(
            name="Nugget User",
            email="nugget@example.com",
            ticket="T456",
            transfer="",
            invitation="",
            jwt="nugget_jwt",
            room_number="600",
            hotel="Nugget",
            can_login=True
        )

        nugget_room = Room.objects.create(
            number="600",
            name_take3="King",
            name_hotel="Nugget",
            is_available=False,
            is_swappable=True,
            primary="Nugget User",
            secondary="",
            guest=nugget_guest
        )

        out, err = self.call_command('600', '--primary=Updated Nugget User', '--hotel-name=Nugget')

        nugget_room.refresh_from_db()
        self.assertEqual(nugget_room.primary, "Updated Nugget User")

    def test_unassign_room_without_guest(self):
        """Test unassigning a room that has no guest"""
        # Create a room without a guest
        unassigned_room = Room.objects.create(
            number="700",
            name_take3="King",
            name_hotel="Ballys",
            is_available=True,
            is_swappable=True,
            primary="",
            secondary="",
            sp_ticket_id="",
            guest=None
        )

        with patch('reservations.management.commands.room_edit.getch', return_value='y'):
            out, err = self.call_command('700', '--unassign', '--hotel-name=Ballys')

        unassigned_room.refresh_from_db()
        self.assertIsNone(unassigned_room.guest)
        self.assertTrue(unassigned_room.is_available)
        self.assertIn("Unassigned room", out)
