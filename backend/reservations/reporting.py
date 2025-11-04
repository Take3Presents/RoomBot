import logging
import os
import sys
import csv

from csv import DictWriter
from reservations.models import Guest, Room, Swap
from django.forms.models import model_to_dict
from reservations.helpers import ts_suffix, egest_csv, take3_date
import reservations.config as roombaht_config

logging.basicConfig(stream=sys.stdout, level=roombaht_config.LOGLEVEL)

logger = logging.getLogger(__name__)


def swaps_report(output_dir=None):
    """Generate swaps CSV. Returns list containing the path to the created file."""
    out_dir = output_dir or roombaht_config.TEMP_DIR
    report_filename = f"swaps-{ts_suffix()}.csv"
    swaps_file = os.path.join(out_dir, report_filename)

    header = [
        'timestamp',
        'room_type',
        'room_one',
        'guest_one_email',
        'room_two',
        'guest_two_email'
    ]
    with open(swaps_file, 'w') as fh:
        writer = DictWriter(fh, fieldnames=header)
        writer.writeheader()
        for swap in Swap.objects.all():
            row = {
                'timestamp': swap.created_at,
                'room_type': swap.room_one.name_take3,
                'room_one': swap.room_one.number,
                'guest_one_email': swap.guest_one.email,
                'room_two': swap.room_two.number,
                'guest_two_email': swap.guest_two.email
            }
            writer.writerow(row)

    return [swaps_file]


def diff_swaps_count():
    """Return the total number of swaps (integer)."""
    return Swap.objects.all().count()


def diff_latest(rows=None, input_file=None, output_dir=None):
    """Compare supplied rows (or input_file CSV) to DB and write a diff CSV.

    Returns list containing the path to the created diff file.
    Also raises ValueError if neither rows nor input_file is provided.
    """
    if rows is None and input_file is None:
        raise ValueError('diff_latest requires either rows or input_file')

    if rows is None and input_file:
        # read CSV into rows (list of dicts) using csv.DictReader
        with open(input_file, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)

    out_dir = output_dir or roombaht_config.TEMP_DIR
    report_filename = f"diff_latest-{ts_suffix()}.csv"
    diff_file = os.path.join(out_dir, report_filename)

    diff_count = 0

    with open(diff_file, 'w') as diffout:
        diffout.write("Things in latest guest list upload but not in the db\n")
        for row in rows:
            existing_ticket = None
            try:
                existing_ticket = Guest.objects.get(ticket=row['ticket_code'])
            except Guest.DoesNotExist:
                pass

            if not existing_ticket:
                diff_count += 1
                diffout.write("%s,%s %s,%s\n" % (row['ticket_code'],
                                                 row.get('first_name', ''),
                                                 row.get('last_name', ''),
                                                 row.get('email', '')))

        diffout.write("Things in db but not in most recent guest list upload\n")
        for guest in Guest.objects.all():
            ticket_found = False
            for row in rows:
                if guest.ticket == row.get('ticket_code'):
                    ticket_found = True
                    break

            if not ticket_found:
                diff_count += 1
                diffout.write(f'{guest.ticket},{guest.name},{guest.email}\n')

    return [diff_file]


def hotel_export(hotel, output_dir=None):
    """Export hotel room assignments to CSV. Returns list containing the path."""
    out_dir = output_dir or roombaht_config.TEMP_DIR

    fields = [
        'room_number',
        'room_type',
        'check_in',
        'check_out',
        'primary_name',
        'secondary_name'
    ]
    rooms = Room.objects.filter(name_hotel=hotel.title())
    if rooms.count() == 0:
        raise Exception("No rooms found for hotel %s" % hotel)

    rows = []
    for room in rooms:
        # some validation

        row = {
            'room_number': room.number,
            'room_type': room.hotel_sku(),
            'primary_name': room.primary
        }
        if room.check_in and room.check_out:
            row['check_in'] = room.check_in
            row['check_out'] = room.check_out
        elif room.check_in and not room.check_out:
            row['check_in'] = room.check_in
            row['check_out'] = 'TBD'
        elif room.check_out and not room.check_in:
            row['check_in'] = 'TBD'
            row['check_out'] = room.check_out
        else:
            row['check_in'] = 'TBD'
            row['check_out'] = 'TBD'

        if getattr(room, 'secondary', '') != '':
            row['secondary_name'] = room.secondary

        rows.append(row)

    report_filename = f"hotel_{hotel.replace(' ', '').lower()}_export-{ts_suffix()}.csv"
    hotel_export_file = os.path.join(out_dir, report_filename)

    egest_csv(rows, fields, hotel_export_file)
    return [hotel_export_file]


def rooming_list_export(hotel, output_dir=None):
    """Export the rooming list for a hotel. Returns list containing the path."""
    out_dir = output_dir or roombaht_config.TEMP_DIR

    rooms = Room.objects.filter(name_hotel=hotel.title())
    if rooms.count() == 0:
        raise Exception("No rooms found for hotel %s" % hotel)

    cols = [
        "room_number",
        "room_type",
        "first_name",
        "last_name",
        "secondary_name",
        "check_in_date",
        "check_out_date",
        "placed_by_roombaht",
        "sp_ticket_id"
    ]

    rows = []
    for room in rooms:
        # hacky split to first/last name
        primary_name = room.primary.split(" ", 1)
        first_name = primary_name[0]
        last_name = primary_name[1] if len(primary_name) > 1 else ""
        row = {
            'room_number': room.number,
            'room_type': room.hotel_sku(),
            'first_name': first_name,
            'last_name': last_name,
        }
        if getattr(room, 'secondary', '') != '':
            row['secondary_name'] = room.secondary
        if room.check_in and room.check_out:
            row['check_in_date'] = take3_date(room.check_in)
            row['check_out_date'] = take3_date(room.check_out)
        elif room.check_in and not room.check_out:
            logger.warning("Room %s missing check out date", room.number)
            row['check_in_date'] = take3_date(room.check_in)
            row['check_out_date'] = 'TBD'
        elif room.check_out and not room.check_in:
            logger.warning("Room %s missing check in date", room.number)
            row['check_in_date'] = 'TBD'
            row['check_out_date'] = take3_date(room.check_out)
        else:
            row['check_in_date'] = 'TBD'
            row['check_out_date'] = 'TBD'
        row["placed_by_roombaht"] = getattr(room, 'placed_by_roombot', None)

        if getattr(room, 'guest', None) and getattr(room.guest, 'ticket', None):
            row['sp_ticket_id'] = room.guest.ticket
        elif getattr(room, 'guest', None) and not getattr(room.guest, 'ticket', None):
            row['sp_ticket_id'] = "n/a"
        else:
            # shouldnt have any of these, but here we are
            logger.warning("No SP ticket state found for room: %s", room.number)
            row['sp_ticket_id'] = ""

        rows.append(row)

    # sort by room number
    sorted_rooms = sorted(rows, key=lambda x: int(x['room_number']))

    report_filename = f"roominglist_hotel_{hotel.replace(' ', '').lower()}-{ts_suffix()}.csv"
    rooming_list_export_file = os.path.join(out_dir, report_filename)
    egest_csv(sorted_rooms, cols, rooming_list_export_file)
    return [rooming_list_export_file]


def dump_guest_rooms(output_dir=None):
    """Dump guest and room tables to two CSVs. Returns list with guest_file then room_file."""
    out_dir = output_dir or roombaht_config.TEMP_DIR
    guest_dump_file = os.path.join(out_dir, f"guest_dump-{ts_suffix()}.csv")
    room_dump_file = os.path.join(out_dir, f"room_dump-{ts_suffix()}.csv")
    guests = Guest.objects.all()
    logger.debug('[-] dumping guests and room tables')
    with open(guest_dump_file, 'w+') as guest_file:
        header = [field.name for field in Guest._meta.fields if field.name != "jwt" and field.name != "invitation"]
        writer = DictWriter(guest_file, fieldnames=header)
        writer.writeheader()
        for guest in guests:
            data = model_to_dict(guest, fields=[field.name for field in guest._meta.fields if field.name != "jwt" and field.name != "invitation"])
            writer.writerow(data)

    rooms = Room.objects.all()
    with open(room_dump_file, 'w+') as room_file:
        header = [field.name for field in Room._meta.fields if field.name != "swap_code" and field.name != "swap_time"]
        writer = DictWriter(room_file, fieldnames=header)
        writer.writeheader()
        for room in rooms:
            data = model_to_dict(room, fields=[field.name for field in room._meta.fields if field.name != "swap_code" and field.name != "swap_time"])
            writer.writerow(data)

    logger.debug('[-] rooms done')
    return [guest_dump_file, room_dump_file]
