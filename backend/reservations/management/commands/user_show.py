from django.core.management.base import BaseCommand, CommandError
from reservations.models import Guest, Staff

class Command(BaseCommand):
    help = "Show information on a guest/user"
    def add_arguments(self, parser):
        parser.add_argument('search',
                            help='The item to search for. Defaults to email.')
        parser.add_argument('--ticket',
                            help='Search by ticket instead of email.',
                            action='store_true',
                            default=False)
        parser.add_argument('--transfer',
                            help='Search by transfer instead of email.',
                            action='store_true',
                            default=False)
        parser.add_argument('--name',
                            help='Search by full name instead of email.',
                            action='store_true',
                            default=False)

    def handle(self, *args, **kwargs):
        if 'search' not in kwargs:
            raise CommandError("Must specify item to search for")

        if (kwargs['ticket'] and (kwargs['transfer'] or kwargs['name'])) \
           or (kwargs['transfer'] and (kwargs['ticket'] or kwargs['name'])) \
           or (kwargs['name'] and (kwargs['ticket'] or kwargs['transfer'])):
            raise CommandError('If searching by other than email must specify only one of --ticket, --transfer, or --name')

        guest_entries = None
        if kwargs['ticket']:
            guest_entries = Guest.objects.filter(ticket=kwargs['search'])
        elif kwargs['transfer']:
            guest_entries = Guest.objects.filter(transfer=kwargs['search'])
        elif kwargs['name']:
            guest_entries = Guest.objects.filter(name=kwargs['search'])
        else:
            guest_entries = Guest.objects.filter(email=kwargs['search'])

        if guest_entries.count() == 0:
            raise CommandError(f"No user found with search term {kwargs['search']} - did you specify right search type?")

        guest = guest_entries[0]
        last_login = 'never'
        if guest.last_login:
            ll = guest.last_login
            last_login = f"{ll.month}/{ll.day}/{ll.year} {ll.hour}:{ll.minute}"

        onboarding = 'no'
        if guest.onboarding_sent:
            onboarding = 'yes'

        rooms = ','.join([f"{x.hotel} {x.room_number}" for x in guest_entries if x.room_number])
        if len(rooms) == 0:
            rooms = 'none'

        tickets = ','.join([x.ticket for x in guest_entries if x.ticket])
        if len(tickets) == 0:
            tickets = 'none'

        adult = ''
        try:
            staff = Staff.objects.get(email=guest.email)
            adult = ' [staff'
            if staff.is_admin:
                adult += ' & admin'

            adult += '],'
        except Staff.DoesNotExist:
            pass

        self.stdout.write(f"User {guest.name},{adult} {guest.email} {guest_entries.count()} records")
        self.stdout.write(f"    otp: {guest.jwt} - can login: {guest.can_login}, last login: {last_login}")
        self.stdout.write(f"    rooms: {rooms}, tickets: {tickets}, onboarding sent: {onboarding}")
