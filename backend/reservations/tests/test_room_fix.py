from io import StringIO
from unittest.mock import patch
from django.test import TestCase
from django.core.management import call_command, CommandError

from reservations.models import Room, Guest


class TestRoomFixCommand(TestCase):
    def setUp(self):
        # original guest and room
        self.orig_guest = Guest.objects.create(
            name="Orig Guest",
            email="orig@example.com",
            ticket="T100",
            transfer="",
            invitation="",
            jwt="orig_jwt",
            room_number="500",
            hotel="Ballys",
            can_login=True
        )

        self.room = Room.objects.create(
            number="500",
            name_take3="King",
            name_hotel="Ballys",
            is_available=False,
            is_swappable=True,
            is_placed=False,
            primary="Orig Guest",
            secondary="",
            sp_ticket_id="T100",
            guest=self.orig_guest,
            placed_by_roombot=False
        )

    def call_command(self, *args, **kwargs):
        out = StringIO()
        err = StringIO()
        call_command('room_fix', *args, stdout=out, stderr=err, **kwargs)
        return out.getvalue(), err.getvalue()

    @patch('reservations.management.commands.room_fix.room_guest_name_mismatch', return_value=True)
    @patch('reservations.management.commands.room_fix.fuzz.ratio')
    def test_fuzzy_matches_update_guest_names(self, mock_fuzz_ratio, mock_mismatch):
        """When fuzz.ratio returns a high match, guest records with same email are updated"""
        # create additional guest entries with same email to be updated
        g1 = Guest.objects.create(name="Orig Guest", email="orig@example.com", ticket="T200")
        g2 = Guest.objects.create(name="Orig Guest", email="orig@example.com", ticket="T300")

        # make fuzz return high for the first occupant and low otherwise
        def fuzz_side_effect(a, b):
            if b == "Better Name":
                return 90
            return 10

        mock_fuzz_ratio.side_effect = fuzz_side_effect

        with patch.object(Room, 'occupants', return_value=["Better Name", "Other Person"]):
            out, err = self.call_command('500', '--hotel-name=Ballys', '--fuzziness=80')

        # all guests with the same email should have been updated to "Better Name"
        updated = list(Guest.objects.filter(email="orig@example.com"))
        self.assertTrue(all(g.name == "Better Name" for g in updated))
        self.assertIn("Updating guest", out)

    @patch('reservations.management.commands.room_fix.room_guest_name_mismatch', return_value=True)
    @patch('reservations.management.commands.room_fix.getch', return_value='q')
    @patch('reservations.management.commands.room_fix.fuzz.ratio', return_value=10)
    def test_interactive_quit_aborts(self, mock_fuzz, mock_getch, mock_mismatch):
        """If user presses 'q' during interactive selection, command aborts cleanly"""
        with patch.object(Room, 'occupants', return_value=["Alice", "Bob"]):
            out, err = self.call_command('500', '--hotel-name=Ballys', '--fuzziness=80')
        self.room.refresh_from_db()
        # room should remain unchanged
        self.assertEqual(self.room.primary, "Orig Guest")
        self.assertIn("Aborting room fix", out)

    @patch('reservations.management.commands.room_fix.room_guest_name_mismatch', return_value=True)
    @patch('reservations.management.commands.room_fix.getch', return_value='1')
    @patch('reservations.management.commands.room_fix.fuzz.ratio', return_value=10)
    def test_select_existing_candidate_with_ticket(self, mock_fuzz, mock_getch, mock_mismatch):
        """Selecting an occupant should associate an existing Guest with matching ticket"""
        # Change original guest's ticket to avoid conflict
        self.orig_guest.ticket = "T999"
        self.orig_guest.save()

        # create a candidate with matching ticket
        candidate = Guest.objects.create(name="Candidate Name", email="cand@example.com", ticket="T100", room_number=None, hotel=None)
        self.room.sp_ticket_id = "T100"
        self.room.save()

        with patch.object(Room, 'occupants', return_value=["Candidate Name"]):
            out, err = self.call_command('500', '--hotel-name=Ballys')

        self.room.refresh_from_db()
        candidate.refresh_from_db()

        self.assertFalse(self.room.is_available)
        self.assertEqual(self.room.primary, candidate.name)
        self.assertEqual(self.room.guest.id, candidate.id)
        self.assertIn("Associated existing guest", out)

    @patch('reservations.management.commands.room_fix.room_guest_name_mismatch', return_value=True)
    @patch('reservations.management.commands.room_fix.getch', return_value='1')
    @patch('reservations.management.commands.room_fix.fuzz.ratio', return_value=10)
    def test_create_new_guest_when_no_candidates(self, mock_fuzz, mock_getch, mock_mismatch):
        """When no suitable candidates exist, a new Guest is created and associated"""
        # ensure no candidates for name
        self.room.sp_ticket_id = ""
        # Keep room.guest set so the command enters the fix logic,
        # but the guest's name won't match any of the new occupants
        self.room.primary = ''
        self.room.save()

        with patch.object(Room, 'occupants', return_value=["New Person"]):
            out, err = self.call_command('500', '--hotel-name=Ballys')

        # first ensure command reported creating a new guest
        self.assertIn("Created new guest", out)

        self.room.refresh_from_db()
        # new guest should have been created and associated
        self.assertTrue(Guest.objects.filter(name="New Person").exists(), f"No guest created; stdout: {out}")
        new_guest = Guest.objects.get(name="New Person")
        self.assertEqual(self.room.primary, "New Person", f"stdout: {out} room.primary after refresh: {self.room.primary}")
        self.assertFalse(self.room.is_available)
        self.assertIsNotNone(self.room.guest)
        self.assertEqual(self.room.guest, new_guest)
