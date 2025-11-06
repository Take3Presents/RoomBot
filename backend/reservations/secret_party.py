import json
import logging
import requests
from typing import Optional, List, Dict, Any, Union
from pathlib import Path
from datetime import datetime, timedelta


class SecretPartyAPIError(Exception):
    pass


class SecretPartyAuthError(SecretPartyAPIError):
    pass


class SecretPartyClient:
    def __init__(self, api_key: str = None, base_url: str = "https://api.secretparty.io"):
        """
        Initialize the Secret Party API client.

        Args:
            api_key: API key for authentication (optional - required only for API calls)
            base_url: Base URL for the API (default: https://api.secretparty.io)
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')

        # Only set up session if we have an API key
        if self.api_key:
            self.session = requests.Session()
            self.session.headers.update({
                'x-mirror-api-key': self.api_key,
                'Content-Type': 'application/json'
            })
        else:
            self.session = None

        # Set up logging
        self.logger = logging.getLogger(__name__)

        # Cache configuration
        from reservations import config as roombaht_config
        self.cache_dir = Path(roombaht_config.CHECK_CACHE_DIR).expanduser()
        self.cache_file = self.cache_dir / 'secret_party_check.json'
        self.cache_max_age = timedelta(hours=1)

    def _read_cache(self) -> Optional[List[Dict[str, Any]]]:
        """
        Read ticket data from cache file if it exists and is fresh.

        Returns:
            List of ticket dictionaries if cache is valid, None otherwise
        """
        if not self.cache_file.exists():
            self.logger.debug(f"Cache file {self.cache_file} does not exist")
            return None

        try:
            cache_mtime = datetime.fromtimestamp(self.cache_file.stat().st_mtime)
            cache_age = datetime.now() - cache_mtime

            if cache_age >= self.cache_max_age:
                self.logger.info(f"Cache expired (age: {cache_age}, max: {self.cache_max_age})")
                return None

            with open(self.cache_file, 'r') as f:
                data = json.load(f)
                self.logger.info(f"Loaded {len(data)} tickets from cache (age: {cache_age})")
                return data

        except (json.JSONDecodeError, IOError, OSError) as e:
            self.logger.warning(f"Failed to read cache file {self.cache_file}: {e}")
            return None

    def _write_cache(self, data: List[Dict[str, Any]]) -> None:
        """
        Write ticket data to cache file.

        Args:
            data: List of ticket dictionaries to cache
        """
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(data, f)
            self.logger.info(f"Cached {len(data)} tickets to {self.cache_file}")
        except Exception as e:
            self.logger.warning(f"Failed to write cache to {self.cache_file}: {e}")

    def export_tickets(
        self,
        order: Optional[str] = None,
        reverse: Optional[bool] = None,
        search: Optional[List[Dict[str, str]]] = None,
        force: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Export tickets from the Secret Party API with caching support.

        Args:
            order: Field to sort by (e.g., "last_name", "first_name", "email", "created_at")
            reverse: Sort in descending order if True
            search: List of search filters to apply
                   Format: [{"label": "status: <status>"}]
            force: If True, bypass cache and fetch from API (default: False)

        Returns:
            List of ticket dictionaries

        Raises:
            SecretPartyAuthError: If authentication fails
            SecretPartyAPIError: If API request fails or no API key provided when needed

        Example:
            # Get all active and transferred tickets (uses cache if available)
            client.export_tickets(order="last_name", reverse=True, search=[])

            # Force fresh data from API
            client.export_tickets(order="last_name", reverse=True, search=[], force=True)
        """
        # Try cache first unless force=True
        if not force:
            cached_data = self._read_cache()
            if cached_data is not None:
                return cached_data

        # Need to fetch from API - require API key
        if not self.api_key or not self.session:
            raise SecretPartyAPIError("API key required to fetch data from Secret Party API")

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
                tickets = data['tickets']
                self.logger.info(f"Successfully retrieved {len(tickets)} tickets")

                # Write to cache
                self._write_cache(tickets)

                return tickets
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
        reverse: bool = True,
        force: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all tickets including "transferred" and "active" status.

        Args:
            order: Field to sort by (default: "last_name")
            reverse: Sort in descending order (default: True)
            force: If True, bypass cache and fetch from API (default: False)

        Returns:
            List of ticket dictionaries for active and transferred tickets
        """
        self.logger.info("Retrieving all active and transferred tickets")
        return self.export_tickets(order=order, reverse=reverse, search=[], force=force)
