"""Abstract base class defining the interface for drone fleet provider integrations.

Concrete implementations (e.g., Skydio) must subclass DroneProvider and implement
all abstract methods. Optional sync methods have default no-op implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProviderCredentials:
    """Authentication credentials for connecting to a drone provider API.

    Attributes:
        api_token: The API authentication token.
        token_id: Optional token identifier (provider-specific).
        base_url: Optional custom API base URL override.
    """
    api_token: str
    token_id: str = ""
    base_url: str = ""


class DroneProvider(ABC):
    """Abstract interface that all drone provider integrations must implement.

    Subclasses must set PROVIDER_NAME and implement all @abstractmethod methods.
    Optional methods (sync_docks, sync_sensor_packages, etc.) return empty lists
    by default and can be overridden when the provider supports them.
    """

    PROVIDER_NAME: str = ""

    @abstractmethod
    def validate_credentials(self, creds: ProviderCredentials) -> bool:
        """Test whether the provided credentials can authenticate with the provider API.

        Args:
            creds: Provider API credentials.

        Returns:
            True if authentication succeeds.
        """
        ...

    @abstractmethod
    def sync_vehicles(self, creds: ProviderCredentials) -> list[dict]:
        """Fetch all vehicles (drones) from the provider.

        Args:
            creds: Provider API credentials.

        Returns:
            List of vehicle data dicts in a normalized format.
        """
        ...

    @abstractmethod
    def sync_flights(self, creds: ProviderCredentials, since: str | None = None) -> list[dict]:
        """Fetch flight records from the provider.

        Args:
            creds: Provider API credentials.
            since: Optional ISO 8601 timestamp to fetch only newer flights.

        Returns:
            List of flight data dicts.
        """
        ...

    @abstractmethod
    def sync_batteries(self, creds: ProviderCredentials) -> list[dict]:
        """Fetch battery inventory and health data from the provider.

        Args:
            creds: Provider API credentials.

        Returns:
            List of battery data dicts.
        """
        ...

    @abstractmethod
    def sync_controllers(self, creds: ProviderCredentials) -> list[dict]:
        """Fetch remote controller records from the provider.

        Args:
            creds: Provider API credentials.

        Returns:
            List of controller data dicts.
        """
        ...

    @abstractmethod
    def get_flight_telemetry(self, creds: ProviderCredentials, flight_id: str) -> list[dict]:
        """Fetch detailed telemetry data for a specific flight.

        Args:
            creds: Provider API credentials.
            flight_id: The provider-specific flight identifier.

        Returns:
            List of telemetry data points.
        """
        ...

    @abstractmethod
    def sync_media(self, creds: ProviderCredentials, since: str | None = None) -> list[dict]:
        """Fetch media (photos/videos) captured during flights.

        Args:
            creds: Provider API credentials.
            since: Optional ISO 8601 timestamp to fetch only newer media.

        Returns:
            List of media metadata dicts.
        """
        ...

    def sync_docks(self, creds: ProviderCredentials) -> list[dict]:
        """Fetch docking station data. Optional; returns empty list by default."""
        return []

    def sync_sensor_packages(self, creds: ProviderCredentials) -> list[dict]:
        """Fetch sensor/payload package data. Optional; returns empty list by default."""
        return []

    def sync_attachments(self, creds: ProviderCredentials) -> list[dict]:
        """Fetch attachment/accessory data. Optional; returns empty list by default."""
        return []

    def sync_users(self, creds: ProviderCredentials) -> list[dict]:
        """Fetch user/pilot accounts from the provider. Optional; returns empty list by default."""
        return []
