import logging
import traceback
from datetime import datetime
from typing import Dict, Any

from .guest_processing_service import GuestProcessingService
from .guest_validation_service import GuestValidationService
from .room_counts import RoomCounts


class GuestIngestionService:

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.guest_processor = GuestProcessingService()
        self.validation_service = GuestValidationService()

    def ingest_from_external_source(self, source_name: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
        self.logger.info(f"Starting guest ingestion from {source_name}")

        try:
            raw_data = self._fetch_from_source(source_name, config)
            transformed_data = self._transform_external_data(raw_data, source_name)
            results = self._process_ingestion_data(transformed_data)
            results['source'] = source_name
            results['ingestion_timestamp'] = datetime.now().isoformat()

            self.logger.info(f"Successfully ingested {results.get('total_processed', 0)} records from {source_name}")
            return results

        except Exception as e:
            self.logger.error(f"Guest ingestion from {source_name} failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'source': source_name,
                'ingestion_timestamp': datetime.now().isoformat()
            }

    def _fetch_from_source(self, source_name: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
        config = config or {}

        if source_name.lower() == 'secretparty':
            return self._fetch_from_secretparty()
        elif source_name.lower() == 'csv':
            return self._fetch_from_csv(config)
        elif source_name.lower() == 'manual':
            return config.get('data', {})
        else:
            raise ValueError(f"Unsupported source: {source_name}")

    def _fetch_from_secretparty(self) -> Dict[str, Any]:
        from ..secret_party import SecretPartyClient, SecretPartyAPIError, SecretPartyAuthError
        from ..config import SP_API_KEY

        self.logger.info("Fetching data from SecretParty API")

        try:
            tickets = SecretPartyClient(SP_API_KEY).export_tickets(
                search=[{"label": "type: add-on"}],
                reverse=True,
                order='purchase_date'
            )

            return {
                'tickets': tickets,
                'metadata': {
                    'fetch_timestamp': datetime.now().isoformat(),
                    'total_records': len(tickets),
                    'source': 'secretparty'
                }
            }

        except (SecretPartyAPIError, SecretPartyAuthError) as e:
            self.logger.error(f"SecretParty API error: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to fetch from SecretParty: {e}")
            raise

    def _fetch_from_csv(self, config: Dict[str, Any]) -> Dict[str, Any]:
        from ..helpers import ingest_csv
        from pathlib import Path

        file_path = config.get('file_path')
        if not file_path or not Path(file_path).exists():
            raise ValueError(f"CSV file not found: {file_path}")

        fields, guests = ingest_csv(file_path)

        self.logger.info(f"Loaded {len(guests)} clean records from CSV with fields: {fields}")

        return {
            'guests': guests,
            'fields': fields,
            'metadata': {
                'source_file': file_path,
                'total_records': len(guests),
                'fields_found': fields
            }
        }

    def _transform_external_data(self, raw_data: Dict[str, Any],
                               source_name: str) -> Dict[str, Any]:
        if source_name.lower() == 'secretparty':
            return self._transform_secretparty_data(raw_data)
        elif source_name.lower() == 'csv':
            return self._transform_csv_data(raw_data)
        elif source_name.lower() == 'manual':
            return raw_data  # Assume already in correct format
        else:
            raise ValueError(f"No transformer for source: {source_name}")

    def _transform_secretparty_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        from ..ingest_models import SecretPartyGuestIngest

        self.logger.info(f"Transforming {len(raw_data.get('tickets', []))} SecretParty tickets")

        transformed_guests = []
        for ticket in raw_data.get('tickets', []):
            try:
                # Use the Pydantic model to handle the transformation
                guest_obj = SecretPartyGuestIngest.from_source(ticket, 'json')

                transformed_guests.append(guest_obj)  # Keep as objects, not dicts

            except Exception as e:
                self.logger.warning(f"Failed to transform ticket {ticket.get('id', 'unknown')}: {e}")
                continue

        self.logger.info(f"Successfully transformed {len(transformed_guests)} tickets to guest records")

        return {
            'guests': transformed_guests,
            'metadata': raw_data.get('metadata', {}),
            'source': 'secretparty'
        }

    def _transform_csv_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        from ..ingest_models import SecretPartyGuestIngest

        guests = []

        for row in raw_data.get('guests', []):
            try:
                # Use the Pydantic model to handle CSV transformation
                guest_obj = SecretPartyGuestIngest.from_source(row, 'csv')
                guests.append(guest_obj)  # Keep as objects, not dicts
            except Exception as e:
                self.logger.warning(f"Failed to transform CSV row: {e}")
                continue

        return {
            'guests': guests
        }

    def _process_ingestion_data(self, transformed_data: Dict[str, Any]) -> Dict[str, Any]:
        guests_data = transformed_data.get('guests', [])

        if not guests_data:
            return {
                'success': True,
                'guests_processed': 0,
                'message': 'No guests to process'
            }

        guests_dict_list = []
        guest_objects_list = []

        for guest in guests_data:
            if hasattr(guest, 'model_dump'):  # Pydantic model
                guests_dict_list.append(guest.model_dump())
                guest_objects_list.append(guest)
            elif isinstance(guest, dict):
                guests_dict_list.append(guest)
                from ..ingest_models import SecretPartyGuestIngest
                guest_obj = SecretPartyGuestIngest(**guest)
                guest_objects_list.append(guest_obj)
            else:
                self.logger.warning(f"Unknown guest data type: {type(guest)}")
                continue

        self.logger.info(f"Validating {len(guests_dict_list)} guests before processing")
        # todo validation should happen on an obj
        valid_guest_dicts = self.validation_service.filter_valid_guests(guests_dict_list)

        valid_guest_ticket_codes = {guest_dict['ticket_code'] for guest_dict in valid_guest_dicts}
        valid_guests = [guest_obj for guest_obj in guest_objects_list
                       if guest_obj.ticket_code in valid_guest_ticket_codes]

        if not valid_guests:
            self.logger.warning("No valid guests after filtering")
            return {
                'success': True,
                'guests_processed': 0,
                'guests_filtered': len(guests_dict_list),
                'message': 'No valid guests after filtering'
            }

        room_counts = RoomCounts()

        from ..services.orphan_reconciliation_service import OrphanReconciliationService
        self.logger.info("Starting orphan reconciliation for %d guest objects", len(valid_guests))
        orphan_tickets = OrphanReconciliationService.reconcile_orphan_rooms(valid_guests, room_counts)
        self.logger.info("Orphan reconciliation complete, found %d orphan tickets", len(orphan_tickets))

        try:
            self.logger.info("Starting guest processing for %d valid guests", len(valid_guests))
            result = self.guest_processor.process_guest_entries(valid_guests, room_counts, orphan_tickets)
            result['room_counts_output'] = room_counts.output()

            result['validation_stats'] = {
                'total_input_guests': len(guests_dict_list),
                'valid_guests': len(valid_guests),
                'filtered_out': len(guests_dict_list) - len(valid_guests)
            }

            result['orphan_stats'] = {
                'orphan_tickets_found': len(orphan_tickets),
                'orphan_tickets': orphan_tickets
            }

            if 'metadata' in transformed_data:
                result['source_metadata'] = transformed_data['metadata']

            self.logger.info("Guest processing complete: %d processed", result.get('total_processed', 0))
            return result

        except Exception as e:
            self.logger.error(f"Guest processing failed: {e}")
            print(traceback.format_exc())
            return {
                'success': False,
                'error': str(e),
                'guests_attempted': len(valid_guests),
                'guests_filtered': len(guests_dict_list) - len(valid_guests),
                'orphan_tickets_attempted': len(orphan_tickets) if 'orphan_tickets' in locals() else 0
            }
