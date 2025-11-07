import json
import tempfile
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.core.management import call_command
from django.test import TestCase

from reservations.models import Guest


class TestSendEmailBlastCommand(TestCase):
    """Test suite for send_email_blast management command"""

    def setUp(self):
        """Create test data"""
        # Create test guests with various configurations
        self.guest1 = Guest.objects.create(
            name="Alice Smith",
            email="alice@example.com",
            hotel="Hilton",
            room_number="101",
            can_login=True
        )

        self.guest2 = Guest.objects.create(
            name="Bob Jones",
            email="bob@example.com",
            hotel="Marriott",
            room_number="202",
            can_login=True
        )

        # Guest with same email as guest1 but different room
        self.guest3 = Guest.objects.create(
            name="Alice Smith",
            email="alice@example.com",
            hotel="Hyatt",
            room_number="303",
            can_login=True
        )

        # Guest without room
        self.guest4 = Guest.objects.create(
            name="Charlie Brown",
            email="charlie@example.com",
            hotel="Hilton",
            room_number=None,
            can_login=True
        )

        # Guest without login
        self.guest5 = Guest.objects.create(
            name="Diana Prince",
            email="diana@example.com",
            hotel="Hilton",
            room_number="404",
            can_login=False
        )

        # Create a test template
        from reservations import models
        self.template_dir = Path(models.__file__).parent / 'templates'
        self.test_template = self.template_dir / 'test_blast.j2'
        self.test_template.write_text(
            "Hello {{ name }}!\nYour email: {{ email }}\n"
            "Rooms: {% for room in rooms %}{{ room }}{% if not loop.last %}, {% endif %}{% endfor %}"
        )

        # Use a temporary state file for tests
        self.state_file = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
        self.state_file_path = Path(self.state_file.name)
        self.state_file.close()

    def tearDown(self):
        """Clean up test data"""
        if self.test_template.exists():
            self.test_template.unlink()
        if self.state_file_path.exists():
            self.state_file_path.unlink()

    @patch('reservations.management.commands.send_email_blast.send_email')
    @patch('reservations.config.SEND_MAIL', True)
    def test_filter_all(self, mock_send_email):
        """Test --all filter sends to all guest emails"""
        with patch('reservations.management.commands.send_email_blast.STATE_FILE_PATH', self.state_file_path):
            mock_send_email.return_value = True

            out = StringIO()
            call_command(
                'send_email_blast',
                '--template', 'test_blast.j2',
                '--subject', 'Test Subject',
                '--all',
                '--batch-size', '10',
                '--batch-time', '0',
                stdout=out
            )

            # Should send to 4 unique emails (alice, bob, charlie, diana)
            assert mock_send_email.call_count == 4

    @patch('reservations.management.commands.send_email_blast.send_email')
    @patch('reservations.config.SEND_MAIL', True)
    def test_filter_email(self, mock_send_email):
        """Test --email filter sends to specific emails"""
        with patch('reservations.management.commands.send_email_blast.STATE_FILE_PATH', self.state_file_path):
            mock_send_email.return_value = True

            out = StringIO()
            call_command(
                'send_email_blast',
                '--template', 'test_blast.j2',
                '--subject', 'Test Subject',
                '--email', 'alice@example.com', 'bob@example.com',
                '--batch-size', '10',
                '--batch-time', '0',
                stdout=out
            )

            # Should send to 2 emails
            assert mock_send_email.call_count == 2

    @patch('reservations.management.commands.send_email_blast.send_email')
    @patch('reservations.config.SEND_MAIL', True)
    def test_filter_eligible(self, mock_send_email):
        """Test --eligible filter sends only to can_login=True and has room"""
        with patch('reservations.management.commands.send_email_blast.STATE_FILE_PATH', self.state_file_path):
            mock_send_email.return_value = True

            out = StringIO()
            call_command(
                'send_email_blast',
                '--template', 'test_blast.j2',
                '--subject', 'Test Subject',
                '--eligible',
                '--batch-size', '10',
                '--batch-time', '0',
                stdout=out
            )

            # Should send to alice and bob only (charlie has no room, diana can't login)
            assert mock_send_email.call_count == 2

    @patch('reservations.management.commands.send_email_blast.send_email')
    @patch('reservations.config.SEND_MAIL', True)
    def test_template_context(self, mock_send_email):
        """Test that template context includes name, email, and rooms list"""
        with patch('reservations.management.commands.send_email_blast.STATE_FILE_PATH', self.state_file_path):
            mock_send_email.return_value = True

            out = StringIO()
            call_command(
                'send_email_blast',
                '--template', 'test_blast.j2',
                '--subject', 'Test Subject',
                '--email', 'alice@example.com',
                '--batch-size', '1',
                '--batch-time', '0',
                stdout=out
            )

            # Get the email body that was sent
            assert mock_send_email.call_count == 1
            call_args = mock_send_email.call_args
            email_body = call_args[0][2]  # third positional argument is body

            # Check that the body contains expected content
            assert "Alice Smith" in email_body
            assert "alice@example.com" in email_body
            # Should have two rooms for alice
            assert "Hilton 101 Alice Smith" in email_body
            assert "Hyatt 303 Alice Smith" in email_body

    @patch('reservations.config.SEND_MAIL', True)
    def test_dry_run(self):
        """Test --dry-run doesn't actually send emails"""
        with patch('reservations.management.commands.send_email_blast.STATE_FILE_PATH', self.state_file_path):
            with patch('reservations.management.commands.send_email_blast.send_email') as mock_send:
                out = StringIO()
                call_command(
                    'send_email_blast',
                    '--template', 'test_blast.j2',
                    '--subject', 'Test Subject',
                    '--email', 'alice@example.com',
                    '--dry-run',
                    '--batch-size', '1',
                    '--batch-time', '0',
                    stdout=out
                )

                # Should not call send_email in dry run
                mock_send.assert_not_called()

                # Should output dry run message
                output = out.getvalue()
                assert '[DRY RUN]' in output

    @patch('reservations.config.SEND_MAIL', False)
    def test_send_mail_disabled_without_force(self):
        """Test that command fails when SEND_MAIL is False without --force"""
        out = StringIO()
        call_command(
            'send_email_blast',
            '--template', 'test_blast.j2',
            '--subject', 'Test Subject',
            '--all',
            stdout=out
        )

        output = out.getvalue()
        assert 'SEND_MAIL is disabled' in output

    @patch('reservations.management.commands.send_email_blast.send_email')
    @patch('reservations.config.SEND_MAIL', False)
    def test_send_mail_disabled_with_force(self, mock_send_email):
        """Test that command works with --force when SEND_MAIL is False"""
        with patch('reservations.management.commands.send_email_blast.STATE_FILE_PATH', self.state_file_path):
            mock_send_email.return_value = True

            out = StringIO()
            call_command(
                'send_email_blast',
                '--template', 'test_blast.j2',
                '--subject', 'Test Subject',
                '--email', 'alice@example.com',
                '--force',
                '--batch-size', '1',
                '--batch-time', '0',
                stdout=out
            )

            output = out.getvalue()
            assert 'WARNING' in output
            assert mock_send_email.call_count == 1

    @patch('reservations.config.SEND_MAIL', True)
    def test_template_not_found(self):
        """Test that command fails gracefully when template doesn't exist"""
        out = StringIO()
        call_command(
            'send_email_blast',
            '--template', 'nonexistent.j2',
            '--subject', 'Test Subject',
            '--all',
            stdout=out
        )

        output = out.getvalue()
        assert 'Template not found' in output

    @patch('reservations.management.commands.send_email_blast.send_email')
    @patch('reservations.config.SEND_MAIL', True)
    def test_state_file_tracking(self, mock_send_email):
        """Test that state file is created and tracks progress"""
        with patch('reservations.management.commands.send_email_blast.STATE_FILE_PATH', self.state_file_path):
            mock_send_email.return_value = True

            out = StringIO()
            call_command(
                'send_email_blast',
                '--template', 'test_blast.j2',
                '--subject', 'Test Subject',
                '--email', 'alice@example.com', 'bob@example.com',
                '--batch-size', '2',
                '--batch-time', '0',
                stdout=out
            )

            # Check state file was created
            assert self.state_file_path.exists()

            with open(self.state_file_path, 'r') as f:
                state = json.load(f)

            assert state['completed'] is True
            assert state['total_emails'] == 2
            assert len(state['sent_emails']) == 2
            assert 'alice@example.com' in state['sent_emails']
            assert 'bob@example.com' in state['sent_emails']

    @patch('reservations.management.commands.send_email_blast.send_email')
    @patch('reservations.config.SEND_MAIL', True)
    def test_template_vars(self, mock_send_email):
        """Test that --template-vars adds variables to context"""
        # Create a template that uses custom variables
        custom_template = self.template_dir / 'test_custom_vars.j2'
        custom_template.write_text("Custom var: {{ custom_var }}")

        try:
            with patch('reservations.management.commands.send_email_blast.STATE_FILE_PATH', self.state_file_path):
                mock_send_email.return_value = True

                out = StringIO()
                call_command(
                    'send_email_blast',
                    '--template', 'test_custom_vars.j2',
                    '--subject', 'Test Subject',
                    '--email', 'alice@example.com',
                    '--template-vars', '{"custom_var": "Hello World"}',
                    '--batch-size', '1',
                    '--batch-time', '0',
                    stdout=out
                )

                # Check that custom var was rendered
                call_args = mock_send_email.call_args
                email_body = call_args[0][2]
                assert "Hello World" in email_body
        finally:
            if custom_template.exists():
                custom_template.unlink()

    @patch('reservations.management.commands.send_email_blast.send_email')
    @patch('reservations.config.SEND_MAIL', True)
    def test_resume_from_state(self, mock_send_email):
        """Test that --resume continues from existing state"""
        # Create a state file with some emails already sent
        initial_state = {
            'command': 'send_email_blast',
            'started_at': datetime.utcnow().isoformat() + 'Z',
            'finished_at': None,
            'template': 'test_blast.j2',
            'subject': 'Test Subject',
            'filter_mode': 'email',
            'total_emails': 2,
            'sent_emails': ['alice@example.com'],
            'failed_emails': [],
            'completed': False
        }

        with open(self.state_file_path, 'w') as f:
            json.dump(initial_state, f)

        with patch('reservations.management.commands.send_email_blast.STATE_FILE_PATH', self.state_file_path):
            mock_send_email.return_value = True

            out = StringIO()
            call_command(
                'send_email_blast',
                '--template', 'test_blast.j2',
                '--subject', 'Test Subject',
                '--email', 'alice@example.com', 'bob@example.com',
                '--resume',
                '--batch-size', '2',
                '--batch-time', '0',
                stdout=out
            )

            # Should only send to bob (alice already sent)
            assert mock_send_email.call_count == 1
            call_args = mock_send_email.call_args
            assert call_args[0][0] == ['bob@example.com']
