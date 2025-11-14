import logging
import sys

from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status
from party.models import Party
from reservations.models import Room
from rest_framework import viewsets
from party.serializers import PartySerializer
import reservations.config as roombaht_config

logging.basicConfig(stream=sys.stdout, level=roombaht_config.LOGLEVEL)
logger = logging.getLogger('ViewLogger_party')

class PartyViewSet(viewsets.ModelViewSet):
    queryset = Party.objects.all()
    serializer_class = PartySerializer
    lookup_field = 'room_number'

    def _check_feature_enabled(self):
        """Return 501 if party feature is disabled"""
        if 'party' not in roombaht_config.FEATURES:
            logger.warning("Access attempt to disabled feature: party")
            return Response(
                {'error': 'Party feature is not enabled'},
                status=status.HTTP_501_NOT_IMPLEMENTED
            )
        return None

    def list(self, request, *args, **kwargs):
        error = self._check_feature_enabled()
        if error:
            return error
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        error = self._check_feature_enabled()
        if error:
            return error
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        error = self._check_feature_enabled()
        if error:
            return error

        room_number = request.data['room_number']
        secret = request.data['secret']
        if secret is None:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        del request.data['secret']

        # we allow looking up the room by
        # * email
        # * primary name
        room = None
        try:
            room = Room.objects.get(name_hotel='Ballys', number=room_number)
            if secret.lower() not in room.primary.lower() and \
               (room.guest is not None and (secret.lower() != room.guest.email.lower())):
                return Response('Must specify the email or name of the room owner', status=status.HTTP_400_BAD_REQUEST)

        except Room.DoesNotExist:
            return Response("This room does not exist - is it in Bally's?", status=status.HTTP_400_BAD_REQUEST)

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        error = self._check_feature_enabled()
        if error:
            return error
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        error = self._check_feature_enabled()
        if error:
            return error

        existing = self.get_object()
        secret = request.data['secret']
        room = Room.objects.get(name_hotel = 'Ballys', number=existing.room_number)
        if secret is None:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        if secret.lower() not in room.primary.lower() and \
               (room.guest is not None and (secret.lower() != room.guest.email.lower())):
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        existing.delete()
        return Response(status=status.HTTP_202_ACCEPTED)
