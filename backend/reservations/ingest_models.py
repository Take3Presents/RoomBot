"""Datatypes for importing guest and room lists"""
# we don't need a StaffImport model because that table is directly translated to the db table

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class SecretPartyGuestIngest(BaseModel):
    """Required fields imported from SecretParty CSV and API
    """
    ticket_code: str  # transaction code for purchase/transfer
    last_name: str
    first_name: str
    email: str
    product: str  # product code, eg name of addon for event, or hotel sku
    transferred_from_code: Optional[str] = None
    type: Optional[str] = None

    @classmethod
    def from_source(cls, data: Dict[str, Any], source_type: str = 'csv') -> 'SecretPartyGuestIngest':
        """Create instance from various data sources"""
        if source_type == 'json' or source_type == 'secretparty':
            return cls._from_json(data)
        elif source_type == 'csv':
            return cls._from_csv(data)
        else:
            raise ValueError(f"Unsupported source type: {source_type}")

    @classmethod
    def _from_json(cls, json_data: Dict[str, Any]) -> 'SecretPartyGuestIngest':
        first_name = json_data.get('first_name', '')
        last_name = json_data.get('last_name', '')

        return cls(
            ticket_code=json_data.get('code', ''),
            last_name=last_name,
            first_name=first_name,
            email=json_data.get('email', ''),
            product=cls._extract_product_name(json_data.get('product')),
            transferred_from_code=cls._extract_transfer_code(json_data.get('transferred_from')),
            type=json_data.get('type')
        )

    @classmethod
    def _from_csv(cls, csv_data: Dict[str, Any]) -> 'SecretPartyGuestIngest':
        return cls(**csv_data)

    @staticmethod
    def _extract_product_name(product_data) -> str:
        if isinstance(product_data, dict):
            return product_data.get('name', '')
        return str(product_data) if product_data else ''

    @staticmethod
    def _extract_transfer_code(transfer_data) -> Optional[str]:
        if isinstance(transfer_data, dict):
            return transfer_data.get('code')
        return transfer_data


class RoomPlacementListIngest(BaseModel):
    """Expected fields in the room spreadsheet
    NOTE: not all of these columns may be used!
    todo: why is that ^^^^^
    """
    placement_verified: Optional[str] = Field(None, alias='Placement Verified')
    room: int = Field(alias='Room')
    room_type: str = Field(alias='Room Type')
    room_features: Optional[str] = Field(alias='Room Features (Accessibility, Lakeview, Smoking)')
    first_name_resident: Optional[str] = Field(alias='First Name (Resident)')
    last_name_resident: Optional[str] = Field(alias='Last Name (Resident)')
    secondary_name: Optional[str] = Field(alias='Secondary Name')
    # check in and out are currently strings, not dates
    check_in_date: Optional[str] = Field(alias='Check-In Date')
    check_out_date: Optional[str] = Field(alias='Check-Out Date')
    placed_by: Optional[str] = Field(alias='Placed By')
    placed_by_roombaht: Optional[str] = Field(alias='Placed By Roombaht')
    ticket_id_in_secret_party: Optional[str] = Field(alias='Ticket ID in SecretParty')
    room_code: Optional[str] = Field(alias='Room Code')

    class Config:
        populate_by_name = True  # allows data to be populated in the model by field names, not just aliases
        extra = 'ignore'  # the model will ignore any additional fields not specified in the model during initialization
