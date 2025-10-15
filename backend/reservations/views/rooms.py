
import os
import logging
import random
import json
import datetime
import sys
from django.core.mail import send_mail
from jinja2 import Environment, PackageLoader
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status
from django.utils.timezone import make_aware
from reservations.models import Guest, Room, SwapError, Swap
from party.models import Party
from ..serializers import *
from ..helpers import phrasing
from ..constants import FLOORPLANS
from reservations.helpers import my_url, send_email
import reservations.config as roombaht_config
from reservations.auth import authenticate, unauthenticated

logging.basicConfig(stream=sys.stdout, level=roombaht_config.LOGLEVEL)

logger = logging.getLogger('ViewLogger_rooms')

@api_view(['POST'])
def my_rooms(request):
    if request.method == 'POST':
        auth_obj = authenticate(request)
        if not auth_obj or 'email' not in auth_obj:
            return unauthenticated()

        email = auth_obj['email']

        try:
            _guest_instances = Guest.objects.filter(email=email)
        except IndexError:
            return Response("No guest or room found", status=status.HTTP_400_BAD_REQUEST)

        rooms = Room.objects.filter(name_hotel__in=roombaht_config.GUEST_HOTELS)
        rooms_mine = [elem for elem in rooms if elem.guest is not None and elem.guest.email==email]

        data = {
            'rooms': [{"number": int(room.number),
                       "type": room.name_take3,
                       "swappable": room.swappable() and not room.cooldown(),
                       "cooldown": room.cooldown(),
                       "hotel": room.hotel_name
                       } for room in rooms_mine],
            'swaps_enabled': roombaht_config.SWAPS_ENABLED,
            'guest_hotels': roombaht_config.GUEST_HOTELS
        }

        logger.debug("rooms for user %s: %s", email, rooms_mine)
        return Response(data)


@api_view(['POST'])
def room_list(request):
    if request.method == 'POST':
        auth_obj = authenticate(request)
        if not auth_obj or 'email' not in auth_obj:
            return unauthenticated()

        email = auth_obj['email']
        logger.debug("Valid guest %s viewing rooms", email)
        # we want to bubble up any room that is swappable, is not available,
        #  is not special (chapel, etc), and does have a guest associated.
        #  the display layer will handle the per-room-type filtering
        rooms = Room.objects \
                    .filter(is_available=False,
                            is_special=False,
                            name_hotel__in=roombaht_config.GUEST_HOTELS) \
                    .exclude(guest=None)
        guest_entries = Guest.objects.filter(email=email)
        room_types = []
        guest_room_numbers = [guest.room_number
                       for guest in guest_entries
                       if guest.room_number is not None]
        for guest_room_number in guest_room_numbers:
            try:
                guest_room = Room.objects.get(number=guest_room_number, name_hotel__in=roombaht_config.GUEST_HOTELS)
                if guest_room.name_take3 not in room_types \
                   and guest_room.swappable() \
                   and not guest_room.cooldown():
                    room_types.append(guest_room.name_take3)
            except Room.DoesNotExist:
                logger.warning("Guest room %s not found for %s", guest_room_number, email)

        if len(room_types) == 0:
            logger.debug("No room types available for guest %s", email)

        not_my_rooms = [x for x in rooms if x.guest.email != email]
        serializer = RoomSerializer(not_my_rooms, context={'request': request}, many=True)
        data = {
            'rooms': serializer.data,
            'swaps_enabled': roombaht_config.SWAPS_ENABLED,
            'guest_hotels': roombaht_config.GUEST_HOTELS
        }

        for room in data['rooms']:
            try:
                if(len(room['number'])==3):
                    room["floorplans"]=FLOORPLANS[int(room["number"][:1])]
                elif(len(room['number'])==4):
                    room["floorplans"]=FLOORPLANS[int(room["number"][:2])]
            except KeyError:
                logger.warning(f"no floor plan found for {room['name_hotel']} / {room['number']}")

            if roombaht_config.SWAPS_ENABLED and room['name_take3'] in room_types:
                room['available']=True
            else:
                room['available']=False

        if 'party' in roombaht_config.FEATURES:
            party_rooms = [x.room_number for x in Party.objects.all()]
            for room in data['rooms']:
                if room['number'] in party_rooms:
                    room['is_party'] = True
                else:
                    room['is_party'] = False

        return Response(data)


@api_view(['POST'])
def room_detail(request, room_number):
    auth_obj = authenticate(request)
    if not auth_obj or 'email' not in auth_obj:
        return unauthenticated()

    hotel = request.query_params.get('hotel', 'ballys').capitalize()
    if hotel not in roombaht_config.GUEST_HOTELS:
        return Response("invalid hotel", status=status.HTTP_400_BAD_REQUEST)
    try:
        room = Room.objects.filter(number=room_number, name_hotel=hotel)
    except Room.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    if request.method == 'POST':
        return Response(RoomSerializer(room[0], context={'request': request}).data)


@api_view(['POST'])
def swap_request(request):
    if request.method == 'POST':
        auth_obj = authenticate(request)
        if not auth_obj or 'email' not in auth_obj:
            return unauthenticated()

        requester_email = auth_obj['email']

        data = request.data

        if not roombaht_config.SWAPS_ENABLED:
            return Response("Room swaps are not currently enabled",
                            status=status.HTTP_501_NOT_IMPLEMENTED)

        try:
            room_num=data["number"]
            name_hotel=data["hotel"]
            msg=data["contact_info"]
        except KeyError:
            return Response("missing fields", status=status.HTTP_400_BAD_REQUEST)

        requester_room_numbers = [x.room_number
                                  for x in Guest.objects.filter(email=requester_email,
                                                                room_number__isnull=False)]

        swap_room = None
        try:
            swap_room = Room.objects.get(number=room_num, name_hotel__in=roombaht_config.GUEST_HOTELS)
        except Room.DoesNotExist:
            return Response("Room not found", status=status.HTTP_404_NOT_FOUND)

        if not swap_room.swappable():
            return Response(f"Room {swap_room.number} is not swappable",
                            status=status.HTTP_400_BAD_REQUEST)

        if swap_room.cooldown():
            return Response(f"Room {swap_room.number} was swapped too recently",
                            status=status.HTTP_400_BAD_REQUEST)


        requester_swappable = []
        for room_number in requester_room_numbers:
            try:
                room = Room.objects.get(number=room_number, name_hotel__in=roombaht_config.GUEST_HOTELS)
                if room.name_take3 == swap_room.name_take3 and room.swappable():
                    requester_swappable.append(room_number)
            except Room.DoesNotExist:
                logger.warning("Guest %s has non existent room %s!",
                               requester_email, room_number)
                continue

        if len(requester_swappable) == 0:
            return Response(f"Requester {requester_email} has no swappable rooms for {room_num}",
                            status=status.HTTP_400_BAD_REQUEST)

        logger.info("[+] Sending swap req from %s to %s with msg: %s",
                    requester_email,
                    swap_room.guest.email,
                    msg)


        objz = {
            'hostname': my_url(),
            'contact_message': msg,
            'room_list': requester_swappable
        }
        jenv = Environment(loader=PackageLoader('reservations'))
        template = jenv.get_template('swap.j2')
        body_text = template.render(objz)

        send_email([swap_room.guest.email],
                   'RoomService RoomBaht - Room Swap Request',
                   body_text)

        return Response("Request sent! They will respond if interested.",
                        status=status.HTTP_201_CREATED)


@api_view(['POST'])
def swap_gen(request):
    if request.method == 'POST':
        auth_obj = authenticate(request)
        if not auth_obj or 'email' not in auth_obj:
            return unauthenticated()
        email = auth_obj['email']

        if not roombaht_config.SWAPS_ENABLED:
            return Response("Room swaps are not currently enabled",
                            status=status.HTTP_501_NOT_IMPLEMENTED)

        data = request.data
        logger.debug(f"data_swap_gen: {data}")
        try:
            room_num=data["number"]["row"]
        except KeyError as e:
            return Response("missing fields", status=status.HTTP_400_BAD_REQUEST)

        try:
            guest_instances = Guest.objects.filter(email=email)
            guest_id = guest_instances[0].id
        except IndexError as e:
            return Response("No guest found", status=status.HTTP_400_BAD_REQUEST)

        room = Room.objects.get(number=room_num, name_hotel__in=roombaht_config.GUEST_HOTELS)

        if not room.swappable():
            return Response(f"Room {room.number} is not swappable",
                            status=status.HTTP_400_BAD_REQUEST)

        if room.guest.id not in [x.id for x in guest_instances]:
            return Response(f"Naughty. Room {room.number} is not your room",
                            status=status.HTTP_400_BAD_REQUEST)

        if room.cooldown():
            return Response(f"Room {room.number} was swapped too recently",
                            status=status.HTTP_400_BAD_REQUEST)

        phrase=phrasing()
        room.swap_code=phrase
        room.swap_code_time=make_aware(datetime.datetime.utcnow())
        room.save()

        logger.info(f"[+] Swap phrase generated {phrase}")
        return Response({"swap_phrase": phrase})


@api_view(['POST'])
def swap_it_up(request):
    if request.method == 'POST':
        auth_obj = authenticate(request)
        if not auth_obj or 'email' not in auth_obj:
            return unauthenticated()
        email = auth_obj['email']

        if not roombaht_config.SWAPS_ENABLED:
            return Response("Room swaps are not currently enabled",
                            status=status.HTTP_501_NOT_IMPLEMENTED)

        data = request.data
        try:
            room_num=data["number"]
            swap_req=data["swap_code"]
        except KeyError as e:
            return Response("missing fields", status=status.HTTP_400_BAD_REQUEST)
            logger.error(f"Missing fields")

        logger.info(f"[+] Swap attempt {data}")
        try:
            guest_instances = Guest.objects.filter(email=email)
            guest_id = guest_instances[0].id
        except IndexError as e:
            logger.warning(f"[+] No guest found")
            return Response("No guest found", status=status.HTTP_400_BAD_REQUEST)

        rooms_swap_match = Room.objects.filter(swap_code=swap_req, name_hotel__in=roombaht_config.GUEST_HOTELS)
        swap_room_mine = Room.objects.filter(number=room_num, name_hotel__in=roombaht_config.GUEST_HOTELS)[0]
        logger.info(f"[+] Swap match {rooms_swap_match}")
        try:
            swap_room_theirs = rooms_swap_match[0]
        except IndexError as e:
            logger.warning("[-] No room matching code")
            return Response("No room matching that code", status=status.HTTP_400_BAD_REQUEST)

        exp_delta = datetime.timedelta(seconds=roombaht_config.SWAP_CODE_LIFE)
        expiration = swap_room_theirs.swap_code_time + exp_delta

        if (expiration.timestamp() < make_aware(datetime.datetime.utcnow()).timestamp()):
            logger.warning("[-] Expired swap code")
            return Response("Expired code", status=status.HTTP_400_BAD_REQUEST)

        if swap_room_mine.cooldown():
            return Response(f"Room {swap_room_mine.number} was swapped too recently",
                            status=status.HTTP_400_BAD_REQUEST)

        if swap_room_theirs.cooldown():
            return Response(f"Room {swap_room_theirs.number} was swapped too recently",
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            Room.swap(swap_room_theirs, swap_room_mine)
        except SwapError:
            return Response("Unable to swap rooms", status=status.HTTP_400_BAD_REQUEST)

        logger.info(f"[+] Weve got a SWAPPA!!! {swap_room_theirs} {swap_room_mine}")

        Swap.log(swap_room_theirs, swap_room_mine)

        return Response(status=status.HTTP_201_CREATED)
