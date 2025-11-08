import pytest
from django.urls import reverse
from waittime.models import Wait


# The router registers the WaitViewSet at 'api/wait', so list is '/api/wait/'


def test_list_waits(api_client, db, make_wait):
    make_wait(name='One', short_name='one')
    make_wait(name='Two', short_name='two')

    resp = api_client.get('/api/wait/')
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(item['short_name'] == 'one' for item in data)


def test_retrieve_wait_without_password(api_client, db, make_wait):
    w = make_wait(name='NoPwd', short_name='nopwd', password=None)
    resp = api_client.get(f'/api/wait/{w.short_name}/')
    assert resp.status_code == 200
    data = resp.json()
    # view only adds has_password when a password exists
    assert 'has_password' not in data
    # serializer should omit password
    assert 'password' not in data


def test_retrieve_wait_with_password(api_client, db, make_wait):
    w = make_wait(name='WithPwd', short_name='withpwd', password='s')
    resp = api_client.get(f'/api/wait/{w.short_name}/')
    assert resp.status_code == 200
    data = resp.json()
    assert data.get('has_password') is True
    assert 'password' not in data


def test_destroy_protected_requires_password(api_client, db, make_wait):
    w = make_wait(name='ToDel', short_name='todel', password='pw')
    # no password provided
    resp = api_client.delete(f'/api/wait/{w.short_name}/')
    assert resp.status_code == 401

    # wrong password
    resp = api_client.delete(f'/api/wait/{w.short_name}/', {'password': 'wrong'}, format='json')
    assert resp.status_code == 401

    # correct password -> accepted
    resp = api_client.delete(f'/api/wait/{w.short_name}/', {'password': 'pw'}, format='json')
    assert resp.status_code == 202
    # object should be deleted
    assert not Wait.objects.filter(short_name=w.short_name).exists()


def test_update_protected_with_password(api_client, db, make_wait):
    w = make_wait(name='Upd', short_name='upd', password='pw', time=3)
    resp = api_client.patch(f'/api/wait/{w.short_name}/', {'time': 10, 'password': 'pw'}, format='json')
    assert resp.status_code == 200
    data = resp.json()
    assert data['time'] == 10
    w.refresh_from_db()
    assert w.time == 10


def test_update_free_update_allows_only_time(api_client, db, make_wait):
    w = make_wait(name='Free', short_name='free', password='pw', time=3, free_update=True)
    # allowed: only time
    resp = api_client.patch(f'/api/wait/{w.short_name}/', {'time': 7}, format='json')
    assert resp.status_code == 200
    w.refresh_from_db()
    assert w.time == 7

    # not allowed: changing name while free_update
    resp = api_client.patch(f'/api/wait/{w.short_name}/', {'time': 8, 'name': 'New'}, format='json')
    # view returns 401 when attempting disallowed changes
    assert resp.status_code == 401
