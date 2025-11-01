
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


def validate_room_params(data):
    """
    Validate and extract room parameters from request data.
    Returns (hotel, number) tuple or Response error.
    """
    hotel = data.get("hotel")
    number_str = data.get("number")

    # Check for missing/empty fields
    if not hotel:
        return Response({"error": "Hotel is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not number_str:
        return Response({"error": "Room number is required"}, status=status.HTTP_400_BAD_REQUEST)

    # Validate number is an integer
    try:
        number = int(number_str)
    except (ValueError, TypeError):
        return Response({"error": "Room number must be a valid integer"}, status=status.HTTP_400_BAD_REQUEST)

    return hotel, number


def swap_error(msg, status=status.HTTP_400_BAD_REQUEST):
    logger.warning(f"Swap Error: {msg}")
    return Response({"error": msg}, status=status)


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

        rooms = Room.objects.filter(name_hotel__in=roombaht_config.VISIBLE_HOTELS)
        rooms_mine = [elem for elem in rooms if elem.guest is not None and elem.guest.email==email]

        data = {
            'rooms': [{"number": int(room.number),
                       "type": room.name_take3,
                       "swappable": room.swappable() and not room.cooldown(),
                       "cooldown": room.cooldown(),
                       "name_hotel": room.name_hotel
                       } for room in rooms_mine],
            'swaps_enabled': roombaht_config.SWAPS_ENABLED,
            'hotels': roombaht_config.VISIBLE_HOTELS
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
                            name_hotel__in=roombaht_config.VISIBLE_HOTELS) \
                    .exclude(guest=None)
        guest_entries = Guest.objects.filter(email=email)
        room_types = []
        guest_room_numbers = [guest.room_number
                       for guest in guest_entries
                       if guest.room_number is not None]
        for guest_room_number in guest_room_numbers:
            guest_rooms = Room.objects.filter(number=guest_room_number,
                                              name_hotel__in=roombaht_config.VISIBLE_HOTELS)
            if guest_rooms.count == 0:
                logger.warning("Guest room %s not found for %s", guest_room_number, email)
            else:
                for guest_room in guest_rooms:
                    if guest_room.name_take3 not in room_types \
                       and guest_room.swappable() \
                       and not guest_room.cooldown():
                        room_types.append(guest_room.name_take3)

        if len(room_types) == 0:
            logger.debug("No room types available for guest %s", email)

        not_my_rooms = [x for x in rooms if x.guest.email != email]
        serializer = RoomSerializer(not_my_rooms, context={'request': request}, many=True)
        data = {
            'rooms': serializer.data,
            'swaps_enabled': roombaht_config.SWAPS_ENABLED,
            'hotels': roombaht_config.GUEST_HOTELS
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
                room['available'] = True
            else:
                room['available'] = False

        if 'party' in roombaht_config.FEATURES:
            party_rooms = [x.room_number for x in Party.objects.all()]
            for room in data['rooms']:
                if room['number'] in party_rooms:
                    room['is_party'] = True
                else:
                    room['is_party'] = False

        return Response(data)


@api_view(['POST'])
def swap_request(request):
    if request.method == 'POST':
        auth_obj = authenticate(request)
        if not auth_obj or 'email' not in auth_obj:
            return unauthenticated()

        requester_email = auth_obj['email']

        data = request.data

        if not roombaht_config.SWAPS_ENABLED:
            return swap_error("Room swaps are not currently enabled",
                              status=status.HTTP_501_NOT_IMPLEMENTED)

        # Validate room parameters
        result = validate_room_params(data)
        if isinstance(result, Response):
            return result
        name_hotel, room_num = result

        # Validate contact_info
        msg = data.get("contact_info")
        if not msg:
            return swap_error("Contact info is required")

        if name_hotel not in roombaht_config.GUEST_HOTELS:
            return swap_error("Room not found", status=status.HTTP_404_NOT_FOUND)

        requester_room_numbers = [x.room_number
                                  for x in Guest.objects.filter(email=requester_email,
                                                                hotel=name_hotel,
                                                                room_number__isnull=False)]

        swap_room = None
        try:
            swap_room = Room.objects.get(number=room_num, name_hotel=name_hotel)
        except Room.DoesNotExist:
            return swap_error("Room not found", status.HTTP_404_NOT_FOUND)

        if not swap_room.swappable():
            return swap_error(f"Room {swap_room} is not swappable")

        if swap_room.cooldown():
            return swap_error(f"Room {swap_room} was swapped too recently")

        requester_swappable = []
        for room_number in requester_room_numbers:
            try:
                room = Room.objects.get(number=room_number,
                                        name_hotel=name_hotel)
                if room.name_take3 == swap_room.name_take3 and room.swappable():
                    requester_swappable.append(room_number)
            except Room.DoesNotExist:
                logger.error("Guest %s has non existent room %s!",
                             requester_email, room_number)
                continue

        if len(requester_swappable) == 0:
            return swap_error(f"Requester {requester_email} has no swappable rooms for {room_num}",
                              status.HTTP_400_BAD_REQUEST)

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

        if send_email([swap_room.guest.email],
                      'RoomService RoomBaht - Room Swap Request',
                      body_text):
            return Response("Request sent! They will respond if interested.",
                            status=status.HTTP_201_CREATED)
        else:
            return swap_error("Unable to send email, please try again later",
                              status.HTTP_500_INTERNAL_SERVER_ERROR)


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

        # Validate room parameters
        result = validate_room_params(data)
        if isinstance(result, Response):
            return result
        hotel, room_num = result

        if hotel not in roombaht_config.VISIBLE_HOTELS:
            return Response("Room not found", status=status.HTTP_404_NOT_FOUND)

        try:
            guest_instances = Guest.objects.filter(email=email)
            guest_id = guest_instances[0].id
        except IndexError as e:
            return swap_error(f"No guest found for room {hotel} {room_num}")

        room = Room.objects.get(number=room_num, name_hotel=hotel)

        if not room.swappable():
            return swap_error(f"Room {hotel} {room_num} is not swappable")

        if room.guest.id not in [x.id for x in guest_instances]:
            return swap_error(f"Naughty. Room {hotel} {room_num} is not your room")

        if room.cooldown():
            return swap_error(f"Room {hotel} {room_num} was swapped too recently")

        phrase=phrasing()
        room.swap_code=phrase
        room.swap_code_time=make_aware(datetime.datetime.utcnow())
        room.save()

        logger.debug(f"[+] Swap phrase generated {phrase}")
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

        # Validate room parameters
        result = validate_room_params(data)
        if isinstance(result, Response):
            return result
        hotel, room_num = result

        # Validate swap_code
        swap_req = data.get("swap_code")
        if not swap_req:
            return swap_error("Swap code is required")

        if hotel not in roombaht_config.VISIBLE_HOTELS:
            return swap_error("Room not in a swappable hotel", status.HTTP_404_NOT_FOUND)

        logger.info(f"[+] Swap attempt {hotel} {room_num}")
        try:
            guest_instances = Guest.objects.filter(email=email)
            guest_id = guest_instances[0].id
        except IndexError as e:
            return swap_error("No guest found")

        rooms_swap_match = Room.objects.filter(swap_code=swap_req, name_hotel__in=roombaht_config.GUEST_HOTELS)
        swap_room_mine = Room.objects.filter(number=room_num, name_hotel=hotel)[0]
        logger.info(f"[+] Swap match {rooms_swap_match}")
        try:
            swap_room_theirs = rooms_swap_match[0]
        except IndexError as e:
            return swap_error("No room matching code")

        exp_delta = datetime.timedelta(seconds=roombaht_config.SWAP_CODE_LIFE)
        expiration = swap_room_theirs.swap_code_time + exp_delta

        if (expiration.timestamp() < make_aware(datetime.datetime.utcnow()).timestamp()):
            return swap_error("Expired code")

        if swap_room_mine.cooldown():
            return swap_error(f"Room {swap_room_mine.number} was swapped too recently")

        if swap_room_theirs.cooldown():
            return swap_error(f"Room {swap_room_theirs.number} was swapped too recently")

        try:
            Room.swap(swap_room_theirs, swap_room_mine)
        except SwapError:
            return swap_error("Unable to swap rooms")

        logger.info(f"[+] Weve got a SWAPPA!!! {swap_room_theirs} {swap_room_mine}")

        Swap.log(swap_room_theirs, swap_room_mine)

        return Response(status=status.HTTP_201_CREATED)
