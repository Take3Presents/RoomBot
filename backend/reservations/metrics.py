"""Metrics calculation functions for RoomBot.

This module provides common metrics calculation functions used by both
the web admin interface and the management command line interface.
"""
import logging
import sys

from django.db.models import Count, Max, Case, When, IntegerField, Q
from reservations.models import Guest, Room
from reservations.constants import ROOM_LIST
from reservations.reporting import diff_swaps_count
import reservations.config as roombaht_config

logging.basicConfig(stream=sys.stdout, level=roombaht_config.LOGLEVEL)
logger = logging.getLogger(__name__)


def calculate_guest_metrics():
    """Calculate guest-related metrics.

    Returns:
        dict: Guest metrics including:
            - guest_count: Total number of guests
            - guest_unique: Number of unique guest emails
            - guest_unplaced: Number of guests without rooms and tickets
    """
    guests = Guest.objects.all()

    guest_count = guests.count()
    guest_unique = len(set([guest.email for guest in guests]))
    guest_unplaced = len(guests.filter(room=None, ticket__isnull=True))

    return {
        'guest_count': guest_count,
        'guest_unique': guest_unique,
        'guest_unplaced': guest_unplaced,
    }


def calculate_room_metrics():
    """Calculate room-related metrics.

    Returns:
        dict: Room metrics including:
            - rooms_count: Total number of rooms
            - rooms_occupied: Number of occupied rooms (not available)
            - rooms_swappable: Number of swappable rooms
            - rooms_available: Number of available rooms
            - rooms_placed_by_roombot: Number of rooms placed by roombot
            - rooms_placed_manually: Number of rooms placed manually
            - rooms_swap_code_count: Number of rooms with swap codes
            - percent_placed: Percentage of rooms occupied
    """
    rooms = Room.objects.all()

    rooms_count = rooms.count()
    rooms_occupied = rooms.exclude(is_available=True).count()
    rooms_swappable = rooms.exclude(is_swappable=False).count()
    rooms_available = rooms.exclude(is_available=False).count()
    rooms_placed_by_roombot = rooms.exclude(placed_by_roombot=False).count()
    rooms_placed_manually = rooms.exclude(placed_by_roombot=True).count()
    rooms_swap_code_count = rooms.filter(swap_code__isnull=False).count()

    if rooms_occupied != 0 and rooms_count != 0:
        percent_placed = round(float(rooms_occupied) / float(rooms_count) * 100, 2)
    else:
        percent_placed = 0

    return {
        'rooms_count': rooms_count,
        'rooms_occupied': rooms_occupied,
        'rooms_swappable': rooms_swappable,
        'rooms_available': rooms_available,
        'rooms_placed_by_roombot': rooms_placed_by_roombot,
        'rooms_placed_manually': rooms_placed_manually,
        'rooms_swap_code_count': rooms_swap_code_count,
        'percent_placed': int(percent_placed),
    }


def calculate_room_type_metrics():
    """Calculate metrics broken down by room type.

    Returns:
        list: List of dicts, each containing:
            - room_type: Display name (hotel - room type)
            - total: Total number of rooms of this type
            - unoccupied: Number of unoccupied rooms of this type
    """
    rooms = Room.objects.all()
    room_metrics = []

    for room_type in ROOM_LIST.keys():
        room_total = rooms.filter(name_take3=room_type).count()
        if room_total > 0:
            room_metrics.append({
                "room_type": f"{ROOM_LIST[room_type]['hotel']} - {room_type}",
                "total": room_total,
                "unoccupied": rooms.filter(name_take3=room_type, is_available=True).count()
            })

    return room_metrics


def calculate_swap_metrics():
    """Calculate swap-related metrics.

    Returns:
        dict: Swap metrics including:
            - rooms_swap_success_count: Total number of successful swaps
    """
    return {
        'rooms_swap_success_count': diff_swaps_count(),
    }


def calculate_onboarding_metrics():
    """Calculate onboarding and per-email (deduplicated) guest metrics.

    Returns:
        dict: Per-email guest metrics including:
            - onboarding_sent_emails: Number of eligible email groups that have been sent onboarding
            - onboarding_pending_emails: Number of eligible email groups waiting for onboarding
            - can_login_emails: Number of email groups that can login
            - users_with_rooms: Number of email groups with assigned rooms
            - known_tickets: Number of email groups with tickets
    """
    # Exclude blank/null emails from per-email metrics
    blank_email_q = Q(email='') | Q(email__isnull=True)
    blank_count = Guest.objects.filter(blank_email_q).count()
    if blank_count > 0:
        # Log a warning and include a small sample of affected guest ids for debugging
        sample_ids = list(Guest.objects.filter(blank_email_q).values_list('id', flat=True)[:10])
        logger.warning(
            "Found %d guest records with blank or null email; excluding them from per-email metrics. Sample ids: %s",
            blank_count, ','.join([str(x) for x in sample_ids])
        )

    # per-email (deduplicated) metrics using OR semantics: an email-group is True if any
    # record with that email has the flag/field. We use annotate + Max(Case(...)) to push
    # the aggregation to the DB. Exclude blank/null emails from grouping.
    email_qs = Guest.objects.exclude(blank_email_q)

    email_groups = email_qs.values('email').annotate(
        onboarding_sent=Max(Case(When(onboarding_sent=True, then=1), default=0, output_field=IntegerField())),
        can_login=Max(Case(When(can_login=True, then=1), default=0, output_field=IntegerField())),
        has_room=Max(Case(When(room__isnull=False, then=1), default=0, output_field=IntegerField())),
        has_ticket=Max(Case(When(Q(ticket__isnull=False) & ~Q(ticket=''), then=1), default=0, output_field=IntegerField())),
    )

    # eligible: only email-groups where they can login AND have rooms
    eligible_groups = email_groups.filter(can_login=1, has_room=1)
    eligible_count = eligible_groups.count()

    # onboarding metrics computed only among eligible email groups
    onboarding_sent_emails = eligible_groups.filter(onboarding_sent=1).count()
    onboarding_pending_emails = eligible_count - onboarding_sent_emails

    # other per-email metrics (not restricted to eligible set)
    can_login_emails = email_groups.filter(can_login=1).count()
    users_with_rooms = email_groups.filter(has_room=1).count()
    known_tickets = email_groups.filter(has_ticket=1).count()

    return {
        'onboarding_sent_emails': onboarding_sent_emails,
        'onboarding_pending_emails': onboarding_pending_emails,
        'can_login_emails': can_login_emails,
        'users_with_rooms': users_with_rooms,
        'known_tickets': known_tickets,
    }


def get_all_metrics():
    """Calculate all metrics and return as a single dict.

    Returns:
        dict: All metrics combined, including:
            - All guest metrics
            - All room metrics
            - All swap metrics
            - All onboarding metrics
            - rooms: List of room type breakdown metrics
            - version: RoomBot version string
    """
    metrics = {}

    # Gather all metrics
    metrics.update(calculate_guest_metrics())
    metrics.update(calculate_room_metrics())
    metrics.update(calculate_swap_metrics())
    metrics.update(calculate_onboarding_metrics())
    metrics['rooms'] = calculate_room_type_metrics()
    metrics['version'] = roombaht_config.VERSION.rstrip()

    return metrics
