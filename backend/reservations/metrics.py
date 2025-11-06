"""Metrics calculation functions for RoomBot.

This module provides common metrics calculation functions used by both
the web admin interface and the management command line interface.
"""
import logging
import sys

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


def get_all_metrics():
    """Calculate all metrics and return as a single dict.

    Returns:
        dict: All metrics combined, including:
            - All guest metrics
            - All room metrics
            - All swap metrics
            - rooms: List of room type breakdown metrics
            - version: RoomBot version string
    """
    metrics = {}

    # Gather all metrics
    metrics.update(calculate_guest_metrics())
    metrics.update(calculate_room_metrics())
    metrics.update(calculate_swap_metrics())
    metrics['rooms'] = calculate_room_type_metrics()
    metrics['version'] = roombaht_config.VERSION.rstrip()

    return metrics
