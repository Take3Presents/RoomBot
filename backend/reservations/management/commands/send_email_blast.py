import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

import reservations.config as roombaht_config
from reservations.helpers import my_url, send_email
from reservations.models import Guest

logging.basicConfig(stream=sys.stdout, level=roombaht_config.LOGLEVEL)
logger = logging.getLogger(__name__)

STATE_FILE_PATH = Path.home() / ".cache" / "roombot" / "email_blast.json"


class Command(BaseCommand):
    help = 'Send templated email blast to (optionally) filtered guest list.' \
        ' Can send to specific emails, all emails, or all "eligible" users' \
        ' (can_login and has at least one room)'

    def add_arguments(self, parser):
        # Required arguments
        parser.add_argument('--template', type=str, required=True,
                            help='Template file name (e.g., swap.j2)')
        parser.add_argument('--subject', type=str, required=True,
                            help='Email subject line')

        # Filtering options (mutually exclusive)
        filter_group = parser.add_mutually_exclusive_group(required=True)
        filter_group.add_argument('--all', action='store_true',
                                  help='Send to all Guest emails in system')
        filter_group.add_argument('--email', nargs='+', type=str,
                                  help='Send to specific email address(es)')
        filter_group.add_argument('--eligible', action='store_true',
                                  help='Send to eligible guests')

        # Batch control
        parser.add_argument('--batch-size', type=int, default=10,
                            help='Number of emails per batch (default: 10)')
        parser.add_argument('--batch-time', type=int, default=300,
                            help='Time to spread batch over in seconds (default: 300)')

        # Template variables
        parser.add_argument('--template-vars', type=str, default='{}',
                            help='Additional template variables as JSON string')

        # State management
        parser.add_argument('--resume', action='store_true',
                            help='Resume from existing state file')
        parser.add_argument('--reset', action='store_true',
                            help='Clear state and start fresh')

        # Safety
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would be sent without sending')
        parser.add_argument('--force', action='store_true',
                            help='Bypass SEND_MAIL config check (with warning)')

    def handle(self, *args, **options):
        # Parse template vars
        try:
            template_vars = json.loads(options['template_vars'])
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f'Invalid JSON in --template-vars: {e}'))
            return

        # Check if SEND_MAIL is enabled
        if not roombaht_config.SEND_MAIL and not options['force']:
            self.stdout.write(self.style.ERROR(
                'SEND_MAIL is disabled in config. Use --force to bypass this check.'))
            return

        if not roombaht_config.SEND_MAIL and options['force']:
            self.stdout.write(self.style.WARNING(
                'WARNING: SEND_MAIL is disabled but --force flag used. Proceeding...'))

        # Validate template exists
        template_path = self._get_template_path(options['template'])
        if not template_path:
            return

        # Handle state file
        STATE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

        if options['reset']:
            if STATE_FILE_PATH.exists():
                STATE_FILE_PATH.unlink()
                self.stdout.write(self.style.SUCCESS('State file cleared.'))

        state = self._load_state()

        if state and not state.get('completed') and not options['resume']:
            self.stdout.write(self.style.ERROR(
                f'Incomplete state file exists at {STATE_FILE_PATH}. '
                'Use --resume to continue or --reset to start fresh.'))
            return

        # Get filtered emails
        emails = self._get_filtered_emails(options)

        if not emails:
            self.stdout.write(self.style.WARNING('No emails match the filter criteria.'))
            return

        # Initialize or update state
        if not options['resume'] or not state:
            state = {
                'command': 'send_email_blast',
                'started_at': datetime.utcnow().isoformat() + 'Z',
                'finished_at': None,
                'template': options['template'],
                'subject': options['subject'],
                'filter_mode': self._get_filter_mode(options),
                'total_emails': len(emails),
                'sent_emails': [],
                'failed_emails': [],
                'completed': False
            }
            self._save_state(state)

        # Remove already sent emails
        remaining_emails = [e for e in emails if e not in state['sent_emails']]

        self.stdout.write(self.style.SUCCESS(
            f'Total emails: {state["total_emails"]}, '
            f'Already sent: {len(state["sent_emails"])}, '
            f'Remaining: {len(remaining_emails)}'))

        if not remaining_emails:
            self.stdout.write(self.style.SUCCESS('All emails already sent!'))
            state['completed'] = True
            state['finished_at'] = datetime.utcnow().isoformat() + 'Z'
            self._save_state(state)
            return

        # Send emails in batches
        self._send_batch(
            remaining_emails,
            options['template'],
            options['subject'],
            template_vars,
            state,
            options['batch_size'],
            options['batch_time'],
            options['dry_run']
        )

        # Mark as completed
        state['completed'] = True
        state['finished_at'] = datetime.utcnow().isoformat() + 'Z'
        self._save_state(state)

        self.stdout.write(self.style.SUCCESS(
            f'\nEmail blast complete! '
            f'Sent: {len(state["sent_emails"])}, '
            f'Failed: {len(state["failed_emails"])}'))

        if state['failed_emails']:
            self.stdout.write(self.style.WARNING('\nFailed emails:'))
            for failed in state['failed_emails']:
                self.stdout.write(f"  {failed['email']}: {failed['error']}")

    def _get_template_path(self, template_name):
        """Validate template exists and return path"""
        # Get the path to reservations/templates
        from reservations import models
        reservations_path = Path(models.__file__).parent
        template_dir = reservations_path / 'templates'
        template_path = template_dir / template_name

        if not template_path.exists():
            self.stdout.write(self.style.ERROR(
                f'Template not found: {template_path}'))
            return None

        return template_path

    def _load_state(self):
        """Load state from JSON file"""
        if not STATE_FILE_PATH.exists():
            return None

        try:
            with open(STATE_FILE_PATH, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f'Error loading state file: {e}')
            return None

    def _save_state(self, state):
        """Save state to JSON file atomically"""
        temp_path = STATE_FILE_PATH.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            json.dump(state, f, indent=2)
        temp_path.replace(STATE_FILE_PATH)

    def _get_filter_mode(self, options):
        """Determine which filter mode is active"""
        if options['all']:
            return 'all'
        elif options['email']:
            return 'email'
        elif options['eligible']:
            return 'eligible'
        return 'unknown'

    def _get_filtered_emails(self, options):
        """Get list of distinct email addresses based on filter"""
        if options['all']:
            emails = Guest.objects.values_list('email', flat=True).distinct()
        elif options['email']:
            emails = Guest.objects.filter(
                email__in=options['email']
            ).values_list('email', flat=True).distinct()
        elif options['eligible']:
            emails = Guest.objects.filter(
                can_login=True,
                room_number__isnull=False
            ).values_list('email', flat=True).distinct()
        else:
            emails = []

        return list(emails)

    def _get_template_context(self, email, template_vars):
        """Build context dict for template rendering"""
        guests = Guest.objects.filter(email=email)

        if not guests.exists():
            return None

        first_guest = guests.first()

        # Build rooms list: "hotel room_number name"
        rooms = [
            f"{g.hotel} {g.room_number} {g.name}"
            for g in guests
            if g.room_number
        ]

        context = {
            'hostname': my_url(),
            'email': email,
            'name': first_guest.name,
            'rooms': rooms,
        }

        # Merge in additional template vars
        context.update(template_vars)

        return context

    def _render_template(self, template_name, context):
        """Render Jinja2 template with context"""
        from reservations import models
        reservations_path = Path(models.__file__).parent
        template_dir = reservations_path / 'templates'

        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template(template_name)
        return template.render(context)

    def _send_batch(self, emails, template_name, subject, template_vars,
                    state, batch_size, batch_time, dry_run):
        """Send emails in batches with timing control"""
        sleep_time = batch_time / batch_size if batch_size > 0 else 0

        for i, email in enumerate(emails):
            # Build context
            context = self._get_template_context(email, template_vars)
            if not context:
                logger.warning(f'No guest found for email: {email}')
                state['failed_emails'].append({
                    'email': email,
                    'error': 'No guest found'
                })
                self._save_state(state)
                continue

            # Render template
            try:
                body = self._render_template(template_name, context)
            except Exception as e:
                logger.error(f'Error rendering template for {email}: {e}')
                state['failed_emails'].append({
                    'email': email,
                    'error': f'Template render error: {str(e)}'
                })
                self._save_state(state)
                continue

            # Send email
            if dry_run:
                self.stdout.write(f'[DRY RUN] Would send to: {email}')
                self.stdout.write(f'  Subject: {subject}')
                self.stdout.write(f'  Context: {context}')
                state['sent_emails'].append(email)
            else:
                success = send_email([email], subject, body)
                if success:
                    logger.info(f'Sent email to {email}')
                    state['sent_emails'].append(email)
                else:
                    logger.error(f'Failed to send email to {email}')
                    state['failed_emails'].append({
                        'email': email,
                        'error': 'send_email returned False'
                    })

            # Save state after each email
            self._save_state(state)

            # Sleep between emails (except after last one)
            if i < len(emails) - 1 and sleep_time > 0:
                time.sleep(sleep_time)
