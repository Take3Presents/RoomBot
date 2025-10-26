import json
import logging
import requests
from typing import Optional, List, Dict, Any, Union


class SecretPartyAPIError(Exception):
    pass


class SecretPartyAuthError(SecretPartyAPIError):
    pass


class SecretPartyClient:
    def __init__(self, api_key: str, base_url: str = "https://api.secretparty.io"):
        """
        Initialize the Secret Party API client.

        Args:
            api_key: API key for authentication
            base_url: Base URL for the API (default: https://api.secretparty.io)
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'x-mirror-api-key': self.api_key,
            'Content-Type': 'application/json'
        })

        # Set up logging
        self.logger = logging.getLogger(__name__)

    def export_tickets(
        self,
        order: Optional[str] = None,
        reverse: Optional[bool] = None,
        search: Optional[List[Dict[str, str]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Export tickets from the Secret Party API.

        Args:
            order: Field to sort by (e.g., "last_name", "first_name", "email", "created_at")
            reverse: Sort in descending order if True
            search: List of search filters to apply
                   Format: [{"label": "status: <status>"}]

        Returns:
            List of ticket dictionaries

        Raises:
            SecretPartyAuthError: If authentication fails
            SecretPartyAPIError: If API request fails

        Example:
            # Get all active and transferred tickets
            client.export_tickets(order="last_name", reverse=True, search=[])

            # Get only transferred tickets
            client.export_tickets(
                order="last_name",
                reverse=True,
                search=[{"label": "status: transferred"}]
            )
        """
        endpoint = f"{self.base_url}/roproxy/organize/tickets/export"

        # Build request payload
        payload = {}
        if order is not None:
            payload['order'] = order
        if reverse is not None:
            payload['reverse'] = reverse
        if search is not None:
            payload['search'] = search
        else:
            payload['search'] = []

        self.logger.info(f"Making POST request to {endpoint}")
        self.logger.debug(f"Request payload: {payload}")

        try:
            response = self.session.post(endpoint, json=payload)

            if response.status_code in [401, 403]:
                self.logger.error("Authentication failed - check API key")
                raise SecretPartyAuthError("Invalid or missing API key")

            if not response.ok:
                msg = f"API request failed: {response.status_code} - {response.text}"
                self.logger.error(msg)
                raise SecretPartyAPIError(msg)

            try:
                data = response.json()
                self.logger.info(f"Successfully retrieved {len(data['tickets'])} tickets")
                return data['tickets']
            except json.JSONDecodeError as e:
                msg = f"Failed to parse JSON response: {e}"
                self.logger.error(msg)
                raise SecretPartyAPIError(msg)

        except requests.exceptions.RequestException as e:
            msg = f"Network error during API request: {e}"
            self.logger.error(msg)
            raise SecretPartyAPIError(msg)

    def get_all_active_and_transferred_tickets(
        self,
        order: str = "last_name",
        reverse: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all tickets including "transferred" and "active" status.

        Args:
            order: Field to sort by (default: "last_name")
            reverse: Sort in descending order (default: True)

        Returns:
            List of ticket dictionaries for active and transferred tickets
        """
        self.logger.info("Retrieving all active and transferred tickets")
        return self.export_tickets(order=order, reverse=reverse, search=[])
