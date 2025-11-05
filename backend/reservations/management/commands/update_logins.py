from django.core.management.base import BaseCommand
from django.db import transaction
from reservations.models import Guest
import reservations.config as roombaht_config

class Command(BaseCommand):
    help = "Enable can_login for guests who should be able to login per guest_drama_check"

    def add_arguments(self, parser):
        parser.add_argument('-n', '--dry-run', action='store_true', help='Show changes without saving')

    def handle(self, *args, **kwargs):
        dry_run = bool(kwargs.get('dry_run'))

        candidates = []
        for guest in Guest.objects.filter(can_login=False):
            try:
                room_count = guest.room_set.count()
            except Exception:
                # Be conservative if counting fails for some reason
                room_count = 0

            if room_count == 1 and guest.hotel in roombaht_config.VISIBLE_HOTELS:
                candidates.append(guest)

        if len(candidates) == 0:
            self.stdout.write('No guests to update')
            return

        self.stdout.write(f"Found {len(candidates)} guests to update")
        for g in candidates:
            self.stdout.write(f" - {g.email} {g.hotel} {g.room_number}")

        if dry_run:
            self.stdout.write('Dry run enabled; no changes made')
            return

        updated = 0
        with transaction.atomic():
            for g in candidates:
                g.can_login = True
                g.save()
                updated += 1

        self.stdout.write(f"Updated {updated} guests to can_login=True")
