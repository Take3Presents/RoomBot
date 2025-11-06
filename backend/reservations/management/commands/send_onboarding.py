import logging
from random import randint
import sys
import time
from django.core.management.base import BaseCommand, CommandError
from jinja2 import Environment, PackageLoader
import reservations.config as roombaht_config
from reservations.models import Guest, Room
from reservations.helpers import my_url, send_email

logging.basicConfig(stream=sys.stdout, level=roombaht_config.LOGLEVEL)
logger = logging.getLogger(__name__)

def onboarding_email(email, otp):
    jenv = Environment(loader=PackageLoader('reservations'))
    template = jenv.get_template('onboarding.j2')
    objz = {
        'hostname': my_url(),
        'email': email,
        'otp': otp,
        'deadline': 'Thursday, November 6th, 2025 at 10pm PST'
    }
    body_text = template.render(objz)
    send_email([email],
               'RoomService RoomBaht - Account Activation',
               body_text)

class Command(BaseCommand):
    help = "Send batches of onboarding emails for guests"
    def add_arguments(self, parser):
        parser.add_argument('-b', '--batch-size',
                            help=f"Batch size to use, defaults to {roombaht_config.ONBOARDING_BATCH}",
                            default=roombaht_config.ONBOARDING_BATCH)
        parser.add_argument('-f', '--force', action='store_true',
                            help='Force sending onboarding emails even if SEND_ONBOARDING is False (will log a warning)')
        parser.add_argument('-e', '--email', action='append',
                            help='Direct lookup email address; may be supplied multiple times')

    def handle(self, *args, **kwargs):
        force = bool(kwargs.get('force'))
        if force:
            logger.warning('Force flag enabled: bypassing SEND_ONBOARDING and sending emails')

        # If direct emails provided, use them instead of random selection
        email_args = kwargs.get('email')
        if email_args:
            # Only include provided emails that have NO Guest with onboarding_sent=True
            # and that meet the other selection criteria (room_number not null, can_login True)
            guest_emails = []
            for e in email_args:
                any_sent = Guest.objects.filter(email=e, onboarding_sent=True).exists()
                if any_sent:
                    logger.debug("Skipping %s because an onboarding email has already been sent", e)
                    continue
                has_pending = Guest.objects.filter(email=e,
                                                   room_number__isnull=False,
                                                   can_login=True).exists()
                if has_pending:
                    guest_emails.append({'email': e})
                else:
                    logger.debug("Skipping %s because it doesn't meet selection criteria", e)
        else:
            guest_emails = Guest.objects \
                .filter(onboarding_sent=False,
                        room_number__isnull=False,
                        can_login=True) \
                .order_by('?') \
                .values('email') \
                .distinct()[:int(kwargs['batch_size'])]

        emails = []
        for guest in guest_emails:
            rooms = Room.objects \
                        .filter(is_placed=False,
                                name_hotel__in=roombaht_config.VISIBLE_HOTELS)
            if len(rooms) > 0:
                emails.append(guest)

        emails_length = len(emails)
        logger.debug("Found %s guests who have not had a onboarding email sent", emails_length)

        if emails_length == 0:
            self.stdout.write("No more activation emails left")

        for email in [x['email'] for x in emails]:
            guests = Guest.objects.filter(email = email)
            # If any guest record already has onboarding_sent True, skip sending to avoid duplicates
            already_onboarded = any(x.onboarding_sent for x in guests)
            if already_onboarded:
                logger.debug("Skipping %s because onboarding has already been sent for this email", email)
                continue

            # At this point none of the guest records for this email have onboarding_sent True
            logger.debug("Activation email for %s has never been sent", email)
            sent_this_email = False
            if not roombaht_config.SEND_ONBOARDING and not force:
                logger.debug("Not actually sending onboarding email to %s", email)
            else:
                if force and not roombaht_config.SEND_ONBOARDING:
                    # additional per-email warning to highlight bypass
                    logger.warning("Force flag used; sending onboarding email to %s despite SEND_ONBOARDING=False", email)
                onboarding_email(email, guests[0].jwt)
                sent_this_email = True

            if sent_this_email:
                not_onboarded = [x for x in guests if not x.onboarding_sent]
                if len(not_onboarded) > 0:
                    logger.debug("Updating onboarding_sent for %s guest records for %s",
                                 len(not_onboarded), email)
                    for guest in not_onboarded:
                        guest.onboarding_sent = True
                        guest.save()

            time.sleep(randint(2, 5))
