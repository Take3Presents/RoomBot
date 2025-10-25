from __future__ import annotations
from csv import DictReader
import datetime
import logging
import sys

from dirtyfields import DirtyFieldsMixin
from django.db import models
from django.utils.timezone import make_aware

import reservations.config as roombaht_config
from reservations.constants import ROOM_LIST
from reservations.helpers import real_date


logging.basicConfig(stream=sys.stdout, level=roombaht_config.LOGLEVEL)
logger = logging.getLogger('__name__')

class SwapError(Exception):
    def __init__(self, msg):
        self.msg = msg
        super().__init__(f"Unable to complete swap: {msg}")

class UnknownProductError(Exception):
    def __init__(self, product):
        self.product = product
        super().__init__(f"Unknown product: {product}")

class Guest(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    name = models.CharField("Name", max_length=240)
    email = models.EmailField()
    ticket = models.CharField("Ticket", max_length=20)
    transfer = models.CharField("Transfer", max_length=20)
    invitation = models.CharField("Invitation", max_length=20)
    jwt = models.CharField("JWT", max_length=240)
    room_number = models.CharField("RoomNumber", max_length=20, blank=True, null=True)
    hotel = models.CharField("Hotel", max_length=20, null=True, blank=True)
    onboarding_sent = models.BooleanField("OnboardingSent", default=False)
    can_login = models.BooleanField("CanLogin", default=False)
    last_login = models.DateTimeField(blank=True, null=True)

    @staticmethod
    def chain(trans_code, guest_chain=[]):
        try:
            existing_guest = Guest.objects.get(ticket=trans_code)
        except Guest.DoesNotExist:
            return guest_chain

        guest_chain.append(existing_guest)
        if existing_guest.transfer:
            return Guest.chain(existing_guest.transfer, guest_chain)

        return guest_chain

    def __str__(self):
        return self.name

class Staff(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    name = models.CharField("Name", max_length=240)
    email = models.EmailField()
    is_admin = models.BooleanField("Admin", default=False)
    guest = models.ForeignKey(Guest, on_delete=models.SET_NULL, blank=True, null=True)

    def __str__(self):
        return f'staff name: {self.name}'


class RoomClassManager(models.Manager):
    def bulk_create_from_csv(self, filename: str) -> None:
        """Bulk create RoomClass records from CSV file

        Returns a list of created RoomClass records.

        """
        fields_for_create = frozenset(["hotel_room_type_code", "hotel_room_type_name"])
        to_create = []

        with open(filename, 'r') as f:
            reader = DictReader(f)
            self._normalize_fieldnames(reader)

            for row in reader:
                # The SP Asset Names field in the Hotel Room Breakdown Key
                # contains one asset name per line, so we split accordingly
                sp_asset_names = row["sp_asset_names"].strip().split("\n")
                for sp_asset_name in sp_asset_names:
                    create_kwargs = {
                        k: v.strip() for k, v in row.items() if k in fields_for_create
                    }
                    create_kwargs["sp_asset_name"] = sp_asset_name
                    create_kwargs["hotel_name"] = self.model.derive_hotel_name(sp_asset_name)
                    to_create.append(self.model(**create_kwargs))


        RoomClass.objects.bulk_create(to_create, ignore_conflicts=True)


    def _normalize_fieldnames(self, reader: DictReader) -> None:
        """Convert input DictReader's fieldnames to expected values

        This is needed because the input CSV fieldnames may include
        the hotel name, and contain spaces and capitalization.

        """
        normalized_fieldnames = []

        for old_fieldname in reader.fieldnames:
            fieldname = old_fieldname.lower().strip()

            if "room type code" in fieldname:
                fieldname = "hotel_room_type_code"
            elif "room type name" in fieldname:
                fieldname = "hotel_room_type_name"
            elif "asset names" in fieldname:
                fieldname = "sp_asset_names"

            normalized_fieldnames.append(fieldname)

        reader.fieldnames = normalized_fieldnames


class RoomClass(DirtyFieldsMixin, models.Model):
    """Represents a class of rooms

    A RoomClass is the database representation of Hotel Room Key data,
    see the Hotel Room Breakdown Key spreadsheet for more details.

    Each RoomClass record is uniquely identified by its Secret Party
    Asset Name and the hotel Room Type Code. Notably, features don't
    apply to RoomClass records, they apply to actual Room records.

    """

    class HotelName(models.TextChoices):
        BALLYS = "Bally's"
        NUGGET = "Nugget"

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sp_asset_name = models.CharField(
        verbose_name="Secret Party Asset Name",
        max_length=255,
    )
    hotel_room_type_code = models.CharField(
        verbose_name="Hotel Room Type Code",
        max_length=20,
    )
    hotel_name = models.CharField(
        verbose_name="Hotel Name",
        max_length=20,
        choices=HotelName.choices,
    )
    hotel_room_type_name = models.CharField(
        verbose_name="Hotel Room Type Name",
        max_length=255,
    )

    objects = RoomClassManager()

    class Meta:
        unique_together = (
            ('sp_asset_name', 'hotel_room_type_code'),
        )

    def __str__(self):
        return f"{self.hotel_name}:{self.hotel_room_type_code}:{self.sp_asset_name}"

    @staticmethod
    def derive_hotel_name(sp_asset_name: str) -> HotelName:
        if "nugget" in sp_asset_name.lower():
            return RoomClass.HotelName.NUGGET

        if "bally's" in sp_asset_name.lower():
            return RoomClass.HotelName.BALLYS

        raise ValueError(f"Could not derive hotel name from asset name: {sp_asset_name}")


class Room(DirtyFieldsMixin, models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    number = models.CharField("Number", max_length=20)
    name_take3 = models.CharField("Take3Name", max_length=50)
    name_hotel = models.CharField("HotelName", max_length=50)
    is_available = models.BooleanField("Available", default=False)
    is_swappable = models.BooleanField("IsSwappable", default=False)
    is_smoking = models.BooleanField("SmokingRoom", default=False)
    is_lakeview = models.BooleanField("LakeviewRoom", default=False)
    is_mountainview = models.BooleanField("MountainviewRoom", default=False)
    is_ada = models.BooleanField("ADA", default=False)
    is_hearing_accessible = models.BooleanField("HearingAccessible", default=False)
    is_special = models.BooleanField("SpecialRoom", default=False)
    is_placed = models.BooleanField("PlacedRoom", default=False)
    swap_code = models.CharField("SwapCode", max_length=200, blank=True, null=True)
    swap_code_time = models.DateTimeField(blank=True, null=True)
    swap_time = models.DateTimeField(blank=True, null=True)
    _check_in = models.DateField(blank=True, null=True, db_column='check_in')
    _check_out = models.DateField(blank=True, null=True, db_column='check_out')
    sp_ticket_id = models.CharField("SecretPartyTicketID", max_length=20, blank=True, null=True)
    primary = models.CharField("PrimaryContact", max_length=200)
    secondary = models.CharField("SecondaryContact", max_length=200)
    placed_by_roombot = models.BooleanField("PlacedByRoombot", default=False)
    guest = models.ForeignKey(Guest, on_delete=models.SET_NULL, blank=True, null=True)

    def __str__(self):
        return str(self.number)

    @property
    def check_out(self):
        return self._check_out

    @check_out.setter
    def check_out(self, value):
        if isinstance(value, datetime.date):
            self._check_out = value
        elif value and value != '':
            self._check_out = real_date(value)
        elif value == '':
            self._check_out = None

    @property
    def check_in(self):
        return self._check_in

    @check_in.setter
    def check_in(self, value):
        if isinstance(value, datetime.date):
            self._check_in = value

        elif value and value != '':
            self._check_in = real_date(value)

        elif value == '':
            self._check_in = None

    def swappable(self):
        return self.guest \
            and self.is_swappable \
            and (not self.is_special)

    def cooldown(self):
        if not self.swap_time:
            return False

        chill_time = self.swap_time \
            + datetime.timedelta(seconds=roombaht_config.ROOM_COOLDOWN)
        right_now = make_aware(datetime.datetime.utcnow())
        return chill_time.timestamp() > right_now.timestamp()

    def hotel_sku(self):
        sku = None
        if self.name_take3 == 'Queen':
            sku = 'Standard 2 Queens'
        elif self.name_take3 == 'Queen Sierra Suite':
            sku = 'Sierra 2 Queens Suite'
        elif self.name_take3 == 'King':
            sku = 'Standard King'
        elif self.name_take3 == 'Queen':
            sku = 'Standard Queen'
        elif self.name_take3 == 'King Sierra Suite':
            sku = 'Sierra King Suite'
        elif self.name_take3 == 'Tahoe Suite':
            sku = 'Tahoe King Suite'
        elif self.name_take3 == 'Executive Suite':
            sku = 'Executive King Suite'
        else:
            sku = self.name_take3

        if self.is_lakeview:
            sku = f"Lakeview {sku}"

        if self.is_smoking:
            sku = f"{sku} (Smoking)"

        access = []
        if self.is_hearing_accessible:
            access.append('Hearing Accessible')

        if self.is_ada:
            access.append('ADA')

        if len(access) > 0:
            sku = (f"{sku} ({','.join(access)})")

        return sku

    @staticmethod
    def short_product_code(product):
        for a_room, a_detail in ROOM_LIST.items():
            if product in a_detail.get('rooms', []):
                return a_room

        if product in ROOM_LIST.keys():
            return product

        raise Exception('Should never not find a short product code tho')

    @staticmethod
    def derive_hotel(product):
        if product.lower().startswith('nugget'):
            return 'Nugget'

        if product.lower().startswith('bally'):
            return 'Ballys'

        raise UnknownProductError(product)

    @staticmethod
    def swap(room_one, room_two):
        if room_two.name_take3 != room_two.name_take3:
            logger.warning("Attempt to swap mismatched room types %s (%s) - %s (%s)",
                           room_one.number, room_two.name_take3,
                           room_two.number, room_two.name_take3)
            raise SwapError('mismatched room type')

        if not room_one.swappable():
            logger.warning("Attempted to swap non swappable room %s %s",
                           room_one.name_hotel, room_one.number)
            raise SwapError('Room one is not swappable')

        if not room_two.swappable():
            logger.warning("Attempted to swap non swappable room %s %s",
                           room_two.name_hotel, room_two.number)
            raise SwapError('Room two is not swappable')

        room_two.guest.room_number = room_one.number
        room_one.guest.room_number = room_two.number

        room_one.swap_code = None
        room_one.swap_code_time = None
        guest_id_theirs = room_one.guest
        room_one.guest = room_two.guest
        room_two.guest = guest_id_theirs

        room_one_primary = room_one.primary
        room_one_secondary = room_one.secondary
        room_one.primary = room_two.primary
        room_two.primary = room_one_primary

        if room_two.secondary:
            room_one.secondary = room_two.secondary

        if room_one.secondary:
            room_two.secondary = room_one_secondary

        room_one_check_in = room_one.check_in
        room_one_check_out = room_one.check_out
        room_one.check_in = room_two.check_in
        room_one.check_out = room_two.check_out
        room_two.check_in = room_one_check_in
        room_two.check_out = room_one_check_out

        room_one_sp_ticket_id = room_one.sp_ticket_id
        room_one.sp_ticket_id = room_two.sp_ticket_id
        room_two.sp_ticket_id = room_one_sp_ticket_id

        # we force this for both rooms to enable swap cooldown time
        room_one.swap_time = make_aware(datetime.datetime.utcnow())
        room_two.swap_time = make_aware(datetime.datetime.utcnow())

        room_two.save()
        room_one.save()

        room_two.guest.save()
        room_one.guest.save()

class Swap(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    room_one = models.ForeignKey(Room, on_delete=models.PROTECT, related_name='+')
    room_two = models.ForeignKey(Room, on_delete=models.PROTECT, related_name='+')
    guest_one = models.ForeignKey(Guest, on_delete=models.PROTECT, related_name='+')
    guest_two = models.ForeignKey(Guest, on_delete=models.PROTECT, related_name='+')

    def __str__(self):
        return f"{self.room_one} <-> {self.room_two}"

    @staticmethod
    def log(room_one, room_two):
        a_swap = Swap()
        a_swap.room_one = room_one
        a_swap.room_two = room_two
        a_swap.guest_one = room_one.guest
        a_swap.guest_two = room_two.guest
        a_swap.save()
        return a_swap
