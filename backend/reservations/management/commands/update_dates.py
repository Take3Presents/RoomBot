import sys
import logging
from django.core.management.base import BaseCommand, CommandError
from reservations.models import Room
from reservations.helpers import real_date
import reservations.config as roombaht_config
from reservations.management import setup_logging

logging.basicConfig(stream=sys.stdout, level=roombaht_config.LOGLEVEL)
logger = logging.getLogger('update_dates')


def changes(room):
    msg = f"{room.name_hotel:9}{room.number:4} changes\n"
    for field, values in room.get_dirty_fields(verbose=True).items():
        saved = values['saved']
        if room.guest and field == 'primary':
            saved = f"{saved} (owner {room.guest.name})"
        msg = f"{msg}    {field} {saved} -> {values['current']}\n"

    return msg


def changes_preview(room, new_check_in, new_check_out):
    """Generate a change summary for dry-run without mutating the model.
    Only includes check_in and check_out fields (the only ones we modify here).
    """
    msg = f"{room.name_hotel:9}{room.number:4} changes\n"

    # check_in
    saved_ci = room.check_in
    curr_ci = new_check_in
    msg = f"{msg}    check_in {saved_ci} -> {curr_ci}\n"

    # check_out
    saved_co = room.check_out
    curr_co = new_check_out
    msg = f"{msg}    check_out {saved_co} -> {curr_co}\n"

    return msg


class Command(BaseCommand):
    help = 'Update check-in/check-out dates for rooms placed_by_roombot with both dates missing'

    def add_arguments(self, parser):
        parser.add_argument('--default-check-in', help='Default check in date (parseable by helpers.real_date)')
        parser.add_argument('--default-check-out', help='Default check out date (parseable by helpers.real_date)')
        parser.add_argument('-d', '--dry-run', help='Do not actually make changes', action='store_true', default=False)
        parser.add_argument('--skip-on-parse-error', help='Skip rooms when date parsing fails instead of aborting', action='store_true', default=False)

    def handle(self, *args, **options):
        self.verbosity = options.get('verbosity', 1)
        setup_logging(self)

        dry_run = options.get('dry_run', False)
        skip_on_parse = options.get('skip_on_parse_error', False)
        default_check_in_raw = options.get('default_check_in')
        default_check_out_raw = options.get('default_check_out')

        # Parse defaults up front to fail fast (or skip if requested)
        parsed_default_check_in = None
        parsed_default_check_out = None

        if default_check_in_raw:
            try:
                parsed_default_check_in = real_date(default_check_in_raw)
                if parsed_default_check_in is None:
                    raise ValueError(f"Could not parse check_in value: {default_check_in_raw!r}")
            except ValueError as e:
                if skip_on_parse:
                    self.stdout.write(self.style.WARNING(f"Failed to parse date for --default-check-in: {default_check_in_raw!r}"))
                    parsed_default_check_in = None
                else:
                    raise CommandError(f"Failed to parse --default-check-in: {e}")

        if default_check_out_raw:
            try:
                parsed_default_check_out = real_date(default_check_out_raw)
                if parsed_default_check_out is None:
                    raise ValueError(f"Could not parse check_out value: {default_check_out_raw!r}")
            except ValueError as e:
                if skip_on_parse:
                    self.stdout.write(self.style.WARNING(f"Failed to parse date for --default-check-out: {default_check_out_raw!r}"))
                    parsed_default_check_out = None
                else:
                    raise CommandError(f"Failed to parse --default-check-out: {e}")

        # If not dry-run, require both defaults (we only update rooms that are missing both dates)
        if not dry_run and (parsed_default_check_in is None or parsed_default_check_out is None):
            raise CommandError('When running non-dry-run both --default-check-in and --default-check-out must be provided and parseable')

        inspected = 0
        updated = 0
        warnings = 0
        parse_errors = 0

        for room in Room.objects.filter(placed_by_roombot=True):
            inspected += 1
            has_check_in = room.check_in is not None
            has_check_out = room.check_out is not None

            # If exactly one date present, warn and skip
            if (has_check_in and not has_check_out) or (has_check_out and not has_check_in):
                warnings += 1
                self.stdout.write(self.style.WARNING(f"Manual reconciliation required for {room.name_hotel} {room.number}: check_in={room.check_in}, check_out={room.check_out}"))
                continue

            # Only modify when both dates missing
            if not has_check_in and not has_check_out:
                # If defaults not parseable (None) then skip (should only happen in dry-run or with skip flag)
                if parsed_default_check_in is None or parsed_default_check_out is None:
                    if skip_on_parse:
                        parse_errors += 1
                        self.stdout.write(self.style.WARNING(f"Failed to parse provided defaults; skipping update for {room.name_hotel} {room.number}"))
                        continue
                    else:
                        # Shouldn't reach here because we validated earlier
                        raise CommandError('Missing parsed defaults while attempting to update')

                if dry_run:
                    # Do not mutate model in dry-run; preview the changes using parsed defaults
                    self.stdout.write(changes_preview(room, parsed_default_check_in, parsed_default_check_out))
                    continue

                # Non-dry-run: Attempt to set via setters to leverage validation
                try:
                    room.check_in = default_check_in_raw if default_check_in_raw is not None else parsed_default_check_in
                    room.check_out = default_check_out_raw if default_check_out_raw is not None else parsed_default_check_out
                except ValueError as e:
                    parse_errors += 1
                    if skip_on_parse:
                        self.stdout.write(self.style.WARNING(f"Failed to parse date for room {room.name_hotel} {room.number}: {e}"))
                        continue
                    else:
                        raise CommandError(f"Failed to parse date for room {room.name_hotel} {room.number}: {e}")

                if room.is_dirty():
                    # persist changes
                    room.save_dirty_fields()
                    updated += 1
                    room_msg = f"Updated {room.name_take3} room {room.number}"
                    self.stdout.write(room_msg)

        # Summary
        self.stdout.write(f"Inspected: {inspected}, Updated: {updated}, Warnings: {warnings}, ParseErrors: {parse_errors}")
