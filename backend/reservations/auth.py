import datetime
import logging
import jwt
import sys
from django.utils.timezone import make_aware
from rest_framework import status
from rest_framework.response import Response
import reservations.config as roombaht_config
from jinja2 import Environment, PackageLoader
from reservations.models import Guest, Staff
from reservations.helpers import send_email, phrasing

logging.basicConfig(stream=sys.stdout, level=roombaht_config.LOGLEVEL)
logger = logging.getLogger('ViewLogger_auth')

def authenticate(request):
    data = request.data
    try:
        jwt_data=data["jwt"]
    except KeyError as e:
        logger.warning("[-] JWT information missing ip:%s data: %s, e: %s", request.META['REMOTE_ADDR'], data, e)
        return None

    try:
        dec = jwt.decode(jwt_data, roombaht_config.JWT_KEY, algorithms="HS256")
    except (TypeError, jwt.exceptions.InvalidSignatureError, jwt.exceptions.DecodeError):
        logger.warning("[-] Unable to decode jwt ip:%s", request.META['REMOTE_ADDR'])
        return None

    dthen = make_aware(datetime.datetime.fromisoformat(dec["datetime"]))
    dnow = make_aware(datetime.datetime.utcnow())

    email = dec['email']
    if dnow - dthen > datetime.timedelta(days=1):
        logger.info("[-] JWT has expired email:%s ip:%s", request.META['REMOTE_ADDR'], email)
        return None

    guest_entries = Guest.objects.filter(email=dec['email'])
    if len(guest_entries) == 0:
        logger.warning("[-] No guest found. email:%s ip:%s", email, request.META['REMOTE_ADDR'])
        return None

    return {'email': email, 'admin': False}

def authenticate_admin(request):
    auth_obj = authenticate(request)
    if not auth_obj or 'email' not in auth_obj:
        return None

    staff = None
    try:
        staff = Staff.objects.get(email=auth_obj['email'])
    except Staff.DoesNotExist:
        logger.warning("[-] No staff found. email:%s ip:%s", auth_obj['email'], request.META['REMOTE_ADDR'])
        return None

    if staff.is_admin:
        auth_obj['admin'] = True

    return auth_obj

def unauthenticated():
    return Response("[-] Unauthorized", status=status.HTTP_401_UNAUTHORIZED)

def do_reset(guests):
    email = guests[0].email
    jenv = Environment(loader=PackageLoader('reservations'))
    template = jenv.get_template('reset.j2')
    new_pass = phrasing()
    objz = {
        'new_pass': new_pass
    }
    body_text = template.render(objz)
    logger.info("Resetting password for %s", email)
    for guest in guests:
        guest.jwt = new_pass
        guest.save()

    send_email([email],
               'RoomService RoomBaht - Password Reset',
               body_text
               )

def reset_otp(email):
    guests = Guest.objects.filter(email=email, can_login=True)
    if guests.count() > 0:
        do_reset(guests)
        return

    else:
        try:
            staff = Staff.objects.get(email=email)
            if staff:
                do_reset(Guest.objects.filter(email=email))
                return

        except Staff.DoesNotExist:
            pass

    logger.warning("Password reset for unknown user %s", email)
