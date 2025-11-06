from django.core.management.base import BaseCommand
from django.db import transaction
from reservations.models import Guest
import reservations.config as roombaht_config

class Command(BaseCommand):
    help = "Enable can_login for guests who should be able to login per guest_drama_check (grouped by email)"

    def add_arguments(self, parser):
        parser.add_argument('-n', '--dry-run', action='store_true', help='Show changes without saving')

    def handle(self, *args, **kwargs):
        dry_run = bool(kwargs.get('dry_run'))

        candidates = []

        # Collect distinct, non-empty emails to consider
        emails = Guest.objects.values_list('email', flat=True).distinct()
        for email in emails:
            if not email:
                continue

            group = Guest.objects.filter(email=email)

            # If any member of the group looks like a visible-hotel single-room guest,
            # then any members of that group with can_login=False should be enabled.
            try:
                visible_single = any(
                    (g.room_set.count() == 1 and g.hotel in roombaht_config.VISIBLE_HOTELS)
                    for g in group
                )
            except Exception:
                # Be conservative if counting fails for some reason
                visible_single = False

            if visible_single:
                for g in group.filter(can_login=False):
                    candidates.append(g)

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
