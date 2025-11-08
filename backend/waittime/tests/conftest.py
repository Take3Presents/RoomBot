import pytest
from rest_framework.test import APIClient
from waittime.models import Wait


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def make_wait(db):
    def _make_wait(**kwargs):
        defaults = {
            'name': kwargs.get('name', 'Test Wait'),
            'short_name': kwargs.get('short_name', 'test'),
            'time': kwargs.get('time', 5),
            'password': kwargs.get('password', None),
            'countdown': kwargs.get('countdown', False),
            'free_update': kwargs.get('free_update', False),
        }
        return Wait.objects.create(**defaults)

    return _make_wait
