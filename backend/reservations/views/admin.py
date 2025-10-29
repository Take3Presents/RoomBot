import os
import logging
import json
import re
import sys

from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import HttpResponse
from rest_framework import status
from reservations.models import Staff
from reservations.models import Guest
from reservations.models import Room
from reservations.reporting import (diff_latest, dump_guest_rooms, swaps_report,
                                    hotel_export, diff_swaps_count, rooming_list_export)
from reservations.helpers import ingest_csv, egest_csv, send_email
from reservations.constants import ROOM_LIST
import reservations.config as roombaht_config
from reservations.auth import authenticate_admin, unauthenticated
from reservations.services.guest_validation_service import GuestValidationService
from reservations.services.guest_ingestion_service import GuestIngestionService

logging.basicConfig(stream=sys.stdout, level=roombaht_config.LOGLEVEL)
logger = logging.getLogger('ViewLogger_admin')


@api_view(['POST'])
def create_guests(request):
    guests_csv = "%s/guestUpload_latest.csv" % roombaht_config.TEMP_DIR
    if request.method == 'POST':
        auth_obj = authenticate_admin(request)
        if not auth_obj or 'email' not in auth_obj or not auth_obj['admin']:
            return unauthenticated()

        ingestion_service = GuestIngestionService()
        config = {'file_path': guests_csv}
        result = ingestion_service.ingest_from_external_source('csv', config)
        room_counts_output = result.get('room_counts_output', [])

        logger.info("guest list uploaded by %s - processed %d guests",
                   auth_obj['email'], result.get('validation_stats', {}).get('valid_guests', 0))

        return Response({'csv_file': guests_csv, 'results': room_counts_output},
                        status=status.HTTP_200_OK)


@api_view(['POST'])
def run_reports(request):
    if request.method == 'POST':
        auth_obj = authenticate_admin(request)
        if not auth_obj or 'email' not in auth_obj or not auth_obj['admin']:
            return unauthenticated()

        logger.info("reports being run by %s", auth_obj['email'])

        admin_emails = [admin.email for admin in Staff.objects.filter(is_admin=True)]
        guest_dump_file, room_dump_file = dump_guest_rooms()
        swaps_file = swaps_report()
        attachments = [
            guest_dump_file,
            room_dump_file,
            swaps_file
        ]
        for hotel in roombaht_config.GUEST_HOTELS:
            attachments.append(hotel_export(hotel))
            attachments.append(rooming_list_export(hotel))

        send_email(admin_emails,
                   'RoomService RoomBaht - Report Time',
                   'Your report(s) are here. *theme song for Brazil plays*',
                   attachments)

        return Response({"admins": admin_emails}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def request_metrics(request):
    if request.method == 'POST':
        auth_obj = authenticate_admin(request)
        if not auth_obj or 'email' not in auth_obj or not auth_obj['admin']:
            return unauthenticated()

        rooooms = Room.objects.all()
        guessssts = Guest.objects.all()

        guest_unique = len(set([guest.email for guest in guessssts]))
        guest_count = Guest.objects.all().count()
        guest_unplaced = len(guessssts.filter(room=None, ticket__isnull=True))

        rooms_count = rooooms.count()
        rooms_occupied = rooooms.exclude(is_available=True).count()
        rooms_swappable = rooooms.exclude(is_swappable=False).count()
        # rooms available: has not yet been placed, roombaht or other
        rooms_available = rooooms.exclude(is_available=False).count()
        # rooms placed by roombot: rooms available to be placed by
        rooms_placed_by_roombot = rooooms.exclude(placed_by_roombot=False).count()
        rooms_placed_manually = rooooms.exclude(placed_by_roombot=True).count()
        rooms_swap_code_count = rooooms.filter(swap_code__isnull=False).count()

        if(rooms_occupied!=0 and rooms_count!=0):
            percent_placed = round(float(rooms_occupied) / float(rooms_count) * 100, 2)
        else:
            percent_placed = 0

        room_metrics = []
        for room_type in ROOM_LIST.keys():
            room_total = rooooms.filter(name_take3=room_type).count()
            if room_total > 0:
                room_metrics.append({
                    "room_type": f"{ROOM_LIST[room_type]['hotel']} - {room_type}",
                    "total": room_total,
                    "unoccupied": rooooms.filter(name_take3=room_type, is_available=True).count()
                })

        metrics = {"guest_count": guest_count,
                   "guest_unique": guest_unique,
                   "guest_unplaced": guest_unplaced,
                   "rooms_count": rooms_count,
                   "rooms_occupied": rooms_occupied,
                   "rooms_swappable": rooms_swappable,
                   "rooms_available": rooms_available,
                   "rooms_placed_by_roombot": rooms_placed_by_roombot,
                   "rooms_placed_manually": rooms_placed_manually,
                   "percent_placed": int(percent_placed),
                   "rooms_swap_code_count": rooms_swap_code_count,
                   "rooms_swap_success_count": diff_swaps_count(),
                   "rooms": room_metrics,
                   "version": roombaht_config.VERSION.rstrip()
                   }

        return Response(metrics, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def guest_file_upload(request):
    if request.method == 'POST':
        data = request.data
        auth_obj = authenticate_admin(request)
        if not auth_obj or 'email' not in auth_obj or not auth_obj['admin']:
            return unauthenticated()

        logger.info("guest data uploaded by %s", auth_obj['email'])

        rows = data['guest_list'].split('\n')
        guest_fields, original_guests = ingest_csv(rows)

        # basic input validation, make sure it's the right csv
        if 'ticket_code' not in guest_fields or \
           'product' not in guest_fields:
            return Response("Unknown file", status=status.HTTP_400_BAD_REQUEST)

        # figure out how to handle sku/product consistently between years
        for o_guest in original_guests:
            raw_product = o_guest['product']
            o_guest['product'] = re.sub(r'[\d\.]+ RS24 ', '', raw_product)

        validation_service = GuestValidationService()
        new_guests = validation_service.filter_valid_guests(original_guests)

        # write out the csv for future use
        egest_csv(new_guests,
                  guest_fields,
                  f"{roombaht_config.TEMP_DIR}/guestUpload_latest.csv")

        first_row = {}
        if len(new_guests) > 0:
            first_row = new_guests[0]

        if len(new_guests) > 0 and len(new_guests) != len(original_guests):
            logger.info("Processing %s new entries: %s",
                        len(new_guests), ','.join([x['ticket_code'] for x in new_guests]))

        resp = str(json.dumps({"received_rows": len(original_guests),
                               "valid_rows": len(new_guests),
                               "diff": diff_latest(new_guests),
                               "headers": guest_fields,
                               "first_row": first_row,
                               "status": "Ready to Load..."
                               }))

        return Response(resp, status=status.HTTP_201_CREATED)

@api_view(['POST'])
def fetch_reports(request):
    if request.method == 'POST':
        auth_obj = authenticate_admin(request)
        if not auth_obj or 'email' not in auth_obj or not auth_obj['admin']:
            return unauthenticated()

    if 'report' not in request.data or \
       'hotel' not in request.data:
        return Response("missing fields", status=status.HTTP_400_BAD_REQUEST)

    if request.data['hotel'].title() not in roombaht_config.GUEST_HOTELS:
        return Response("unknown hotel", status=status.HTTP_400_BAD_REQUEST)

    export_file = None
    if request.data['report'] == 'hotel':
        export_file = hotel_export(request.data['hotel'])
    elif request.data['report'] == 'roomslist':
        export_file = rooming_list_export(request.data['hotel'])
    elif request.data['report'] == 'room':
        _guest_file, export_file = dump_guest_rooms()
    elif request.data['report'] == 'guest':
        export_file, _room_file = dump_guest_rooms()
    elif request.data['report'] == 'swaps':
        export_file = swaps_report()
    else:
        return Response("unknown report", status=status.HTTP_400_BAD_REQUEST)

    response = HttpResponse(open(export_file, 'r'), content_type='text/csv')
    response['Content-Disposition'] = f"attachment; filename={os.path.basename(export_file)}"

    return response
