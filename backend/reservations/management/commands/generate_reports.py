from django.core.management.base import BaseCommand, CommandError
import reservations.reporting as reporting
import reservations.config as roombaht_config
from reservations.helpers import ts_suffix
import os


VALID_REPORTS = [
    'swaps',
    'hotel_export',
    'rooming_list',
    'dump_guest_rooms',
    'diff_latest',
    'diff_swaps_count'
]


class Command(BaseCommand):
    help = 'Generate CSV reports from reservations.reporting'

    def add_arguments(self, parser):
        parser.add_argument('-r', '--reports', action='append', help='Report names to generate. Repeatable or comma-separated. Defaults to all.')
        parser.add_argument('-H', '--hotel', help='Hotel name for hotel-specific reports (hotel_export, rooming_list)')
        parser.add_argument('-o', '--output-dir', help='Directory to write CSVs (default from config)')
        parser.add_argument('--overwrite', action='store_true', help='If set, allow overwriting existing files (default is timestamped filenames)')

    def handle(self, *args, **options):
        reports_opt = options.get('reports')
        if not reports_opt:
            selected = VALID_REPORTS.copy()
        else:
            # normalize comma-separated or repeatable
            selected = []
            for item in reports_opt:
                for part in item.split(','):
                    p = part.strip()
                    if p:
                        selected.append(p)

        invalid = [r for r in selected if r not in VALID_REPORTS]
        if invalid:
            raise CommandError(f'Invalid report names: {invalid}. Valid: {VALID_REPORTS}')

        outdir = options.get('output_dir') or roombaht_config.TEMP_DIR
        if not os.path.isdir(outdir):
            raise CommandError(f'Output directory does not exist: {outdir}')

        results = []

        for rep in selected:
            if rep == 'swaps':
                files = reporting.swaps_report(output_dir=outdir)
                results.extend(files)
            elif rep == 'hotel_export':
                hotel = options.get('hotel')
                if not hotel:
                    raise CommandError('hotel_export requires --hotel')
                files = reporting.hotel_export(hotel, output_dir=outdir)
                results.extend(files)
            elif rep == 'rooming_list':
                hotel = options.get('hotel')
                if not hotel:
                    raise CommandError('rooming_list requires --hotel')
                files = reporting.rooming_list_export(hotel, output_dir=outdir)
                results.extend(files)
            elif rep == 'dump_guest_rooms':
                files = reporting.dump_guest_rooms(output_dir=outdir)
                results.extend(files)
            elif rep == 'diff_latest':
                # diff_latest expects rows or input_file; for CLI we will operate on DB only
                # raising unless user wants to provide a file in future
                raise CommandError('diff_latest is not supported from CLI without an input file')
            elif rep == 'diff_swaps_count':
                count = reporting.diff_swaps_count()
                # write a small file with the count
                filename = os.path.join(outdir, f'diff_swaps_count-{__import__("reservations.helpers").helpers.ts_suffix()}.txt')
                with open(filename, 'w') as fh:
                    fh.write(str(count) + '\n')
                results.append(filename)

        for path in results:
            self.stdout.write(path)
