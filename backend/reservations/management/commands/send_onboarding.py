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

    def handle(self, *args, **kwargs):
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
            onboarded = [x for x in guests if x.onboarding_sent]
            if len(onboarded) == 0:
                logger.debug("Activation email for %s has never been sent", email)
                if not roombaht_config.SEND_ONBOARDING:
                    logger.debug("Not actually sending onboarding email to %s", email)
                else:
                    onboarding_email(email, guests[0].jwt)

            not_onboarded = [x for x in guests if not x.onboarding_sent]
            if len(not_onboarded) > 0:
                logger.debug("Updating onboarding_sent for %s guest records for %s",
                             len(not_onboarded), email)
                for guest in not_onboarded:
                    guest.onboarding_sent = True
                    guest.save()

            time.sleep(randint(2, 5))
