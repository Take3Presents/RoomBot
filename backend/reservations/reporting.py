import logging
import os
import sys

from csv import DictWriter
from reservations.models import Guest, Room, Swap
from django.forms.models import model_to_dict
from reservations.helpers import ts_suffix, egest_csv, take3_date
import reservations.config as roombaht_config

logging.basicConfig(stream=sys.stdout, level=roombaht_config.LOGLEVEL)

logger = logging.getLogger(__name__)

def swaps_report():
    swaps_file = f"{roombaht_config.TEMP_DIR}/swaps-{ts_suffix()}.csv"
    header = [
        'timestamp',
        'room_type',
        'room_one',
        'guest_one_email',
        'room_two',
        'guest_two_email'
    ]
    writer = DictWriter(open(swaps_file, 'w'), fieldnames=header)
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

    return swaps_file

def diff_swaps_count():
    return Swap.objects.all().count()

def diff_latest(rows):
    diff_count = 0

    with open(f"{roombaht_config.TEMP_DIR}/diff_latest.csv", 'w') as diffout:
        guests = Guest.objects.all()
        diffout.write("Things in latest guest list upload but not in the db\n")
        for row in rows:
            existing_ticket = None
            try:
                existing_ticket = Guest.objects.get(ticket=row['ticket_code'])
            except Guest.DoesNotExist:
                pass

            if not existing_ticket:
                diff_count+=1
                diffout.write("%s,%s %s,%s\n" % (row['ticket_code'],
                                                 row['first_name'],
                                                 row['last_name'],
                                                 row['email']))

        diffout.write("Things in db but not in most recent guest list upload\n")
        for guest in guests:
            ticket_found = False
            for row in rows:
                if guest.ticket == row['ticket_code']:
                    ticket_found = True
                    break

            if ticket_found:
                diff_count+=1
                diffout.write(f'{guest.ticket},{guest.name},{guest.email}\n')

    return diff_count

def hotel_export(hotel):
    fields = [
        'room_number',
        'room_type',
        'check_in',
        'check_out',
        'primary_name',
        'secondary_name'
    ]
    rooms = Room.objects.filter(name_hotel = hotel.title())
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

        if room.secondary != '':
            row['secondary_name'] = room.secondary

        rows.append(row)

    hotel_export_file = f"{roombaht_config.TEMP_DIR}/hotel_{hotel.lower()}_export-{ts_suffix()}.csv"
    report_filename = f"hotel_{hotel.replace(' ', '').lower()}_export-{ts_suffix()}.csv"
    hotel_export_file = os.path.join(roombaht_config.TEMP_DIR, report_filename)

    egest_csv(rows, fields, hotel_export_file)
    return hotel_export_file


def rooming_list_export(hotel):
    rooms = Room.objects.filter(name_hotel = hotel.title())
    if rooms.count() == 0:
        msg = "No rooms found for hotel %s" % hotel
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
        last_name = primary_name[1] if len(primary_name)>1 else ""
        row = {
            'room_number': room.number,
            'room_type': room.hotel_sku(),
            'first_name': first_name,
            'last_name': last_name,
        }
        if room.secondary != '':
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
        row["placed_by_roombaht"] = room.placed_by_roombot

        if room.guest and room.guest.ticket:
            row['sp_ticket_id'] = room.guest.ticket
        elif room.guest and not room.guest.ticket:
            row['sp_ticket_id'] = "n/a"
        else:
            # shouldnt have any of these, but here we are
            logger.warning("No SP ticket state found for room: %s",  room.number)
            row['sp_ticket_id'] = ""

        rows.append(row)

    # sort by room number
    sorted_rooms = sorted(rows, key=lambda x: int(x['room_number']))

    report_filename = f"roominglist_hotel_{hotel.replace(' ', '').lower()}-{ts_suffix()}.csv"
    rooming_list_export_file = os.path.join(roombaht_config.TEMP_DIR, report_filename)
    egest_csv(sorted_rooms, cols, rooming_list_export_file)
    return rooming_list_export_file

def dump_guest_rooms():
    guest_dump_file = f"{roombaht_config.TEMP_DIR}/guest_dump-{ts_suffix()}.csv"
    room_dump_file = f"{roombaht_config.TEMP_DIR}/room_dump-{ts_suffix()}.csv"
    guests = Guest.objects.all()
    logger.debug(f'[-] dumping guests and room tables')
    with open(guest_dump_file, 'w+') as guest_file:
        header = [field.name for field in Guest._meta.fields if field.name!="jwt" and field.name!="invitation"]
        writer = DictWriter(guest_file, fieldnames=header)
        writer.writeheader()
        for guest in guests:
            data = model_to_dict(guest, fields=[field.name for field in guest._meta.fields if field.name!="jwt" and field.name!="invitation"])
            writer.writerow(data)

    rooms = Room.objects.all()
    with open(room_dump_file, 'w+') as room_file:
        header = [field.name for field in Room._meta.fields if field.name!="swap_code" and field.name!="swap_time"]
        writer = DictWriter(room_file, fieldnames=header)
        writer.writeheader()
        for room in rooms:
            data = model_to_dict(room, fields=[field.name for field in room._meta.fields if field.name!="swap_code" and field.name!="swap_time"])
            writer.writerow(data)

    logger.debug(f'[-] rooms done')
    return guest_dump_file, room_dump_file
