from django.core.checks import Error, Warning, Info, register, Tags
from reservations.models import Room, Guest
from reservations import config as roombaht_config
from reservations.constants import ROOM_LIST
from reservations.secret_party import SecretPartyClient
from reservations.ingest_models import SecretPartyGuestIngest


@register(Tags.database, deploy=True)
def secret_party_data_check(app_configs, **kwargs):
    """Check database state against Secret Party source data to detect missing room assignments."""

    if not roombaht_config.SP_SYSTEM_CHECKS:
        return [Info("Skipping secret party data check",
                     hint='This check does not run in tests or CI')]

    errors = []

    # Build set of all room product names from ROOM_LIST
    room_products = set()
    for room_type, room_data in ROOM_LIST.items():
        room_products.update(room_data['rooms'])

    # Use SecretPartyClient with cache support
    # Initialize without API key first - will use cache if available
    api_key = roombaht_config.SP_API_KEY if roombaht_config.SP_API_KEY else None
    client = SecretPartyClient(api_key=api_key)

    try:
        # Try to get data - will use cache if available, otherwise fetch from API
        sp_data = client.export_tickets(order="last_name",
                                        reverse=True,
                                        search=[
                                            {"label": "status:active"}
                                        ])

    except Exception as e:
        # If we have no API key and no cache, this is expected
        if not roombaht_config.SP_API_KEY:
            errors.append(Warning(
                "SP_API_KEY not configured and no cached data available",
                hint="Set ROOMBAHT_SP_API_KEY environment variable to enable this check"
            ))
        else:
            errors.append(Warning(
                f"Failed to fetch Secret Party data: {e}",
                hint="Check API key and network connectivity. System check will be skipped."
            ))
        return errors

    # Process Secret Party data and compare with database
    transferred_tickets = set(Guest.objects.exclude(transfer='').exclude(transfer__isnull=True).values_list('transfer', flat=True))

    for ticket_data in sp_data:
        try:
            guest_obj = SecretPartyGuestIngest.from_source(ticket_data, source_type='json')

            # Skip if not a room product
            if guest_obj.product not in room_products:
                continue

            ticket_code = guest_obj.ticket_code

            # Check if this ticket was transferred away (intermediate in chain)
            if ticket_code in transferred_tickets:
                continue  # Intermediate guests shouldn't have rooms

            # This is a tail guest with a room product - they should have a room assignment
            try:
                guest = Guest.objects.get(ticket=ticket_code)

                # Check if they have a room assigned
                if guest.room_number is None and guest.room_set.count() == 0:
                    errors.append(Error(
                        f"(ticket {ticket_code}) has room product '{guest_obj.product}' in Secret Party but no room assigned in database",
                        hint="Room assignment may have failed during ingestion. Consider re-running ingestion or manual assignment.",
                        obj=guest
                    ))
                elif guest.room_number is not None and guest.room_set.count() == 0:
                    errors.append(Error(
                        f"(ticket {ticket_code}) has room_number='{guest.room_number}' but no Room object with associated guest",
                        hint="Database inconsistency - room_number is set but Room.guest is missing.",
                        obj=guest
                    ))

            except Guest.DoesNotExist:
                errors.append(Warning(
                    f"Ticket {ticket_code} with room product '{guest_obj.product}' exists in Secret Party but not in database",
                    hint="Guest may not have been ingested yet. Fetch secret party data via command or admin page."
                ))
            except Guest.MultipleObjectsReturned:
                errors.append(Error(
                    f"Multiple Guest records found for ticket {ticket_code}",
                    hint="Database corruption - duplicate ticket codes exist."
                ))

        except Exception as e:
            errors.append(Warning(
                f"Error processing Secret Party ticket data: {e}",
                hint="Check data format and ingestion models"
            ))

    return errors


