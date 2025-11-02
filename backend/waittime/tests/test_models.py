import pytest
from django.db import IntegrityError
from waittime.models import Wait


def test_wait_creation_defaults(db):
    w = Wait.objects.create(name='A', short_name='a-defaults', time=10)
    assert w.countdown is False
    assert w.free_update is False
    assert w.created_at is not None
    assert w.updated_at is not None


def test_short_name_unique(db):
    Wait.objects.create(name='First', short_name='dup-short', time=1)
    with pytest.raises(IntegrityError):
        # unique constraint on short_name should raise on second create
        Wait.objects.create(name='Second', short_name='dup-short', time=2)
