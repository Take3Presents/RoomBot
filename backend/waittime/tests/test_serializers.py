import pytest
from waittime.serializers import WaitSerializer, WaitViewSerializer, WaitListSerializer
from waittime.models import Wait


def test_wait_serializer_fields(db):
    w = Wait.objects.create(name='A', short_name='a-ser', time=5, password='p', countdown=True, free_update=True)
    s = WaitSerializer(w)
    data = s.data
    assert 'password' in data
    assert data['time'] == 5


def test_wait_view_serializer_omits_password(db):
    w = Wait.objects.create(name='A', short_name='a-view', time=5, password='secret')
    s = WaitViewSerializer(w)
    data = s.data
    assert 'password' not in data


def test_wait_list_serializer_fields(db):
    w = Wait.objects.create(name='ListName', short_name='list-sn', time=1)
    s = WaitListSerializer([w], many=True)
    data = s.data
    assert isinstance(data, list)
    assert 'name' in data[0] and 'short_name' in data[0]
    # list serializer should not include time field
    assert 'time' not in data[0]
