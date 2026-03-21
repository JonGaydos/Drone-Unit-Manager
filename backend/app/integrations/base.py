from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProviderCredentials:
    api_token: str
    token_id: str = ""
    base_url: str = ""


class DroneProvider(ABC):
    PROVIDER_NAME: str = ""

    @abstractmethod
    def validate_credentials(self, creds: ProviderCredentials) -> bool:
        ...

    @abstractmethod
    def sync_vehicles(self, creds: ProviderCredentials) -> list[dict]:
        ...

    @abstractmethod
    def sync_flights(self, creds: ProviderCredentials, since: str | None = None) -> list[dict]:
        ...

    @abstractmethod
    def sync_batteries(self, creds: ProviderCredentials) -> list[dict]:
        ...

    @abstractmethod
    def sync_controllers(self, creds: ProviderCredentials) -> list[dict]:
        ...

    @abstractmethod
    def get_flight_telemetry(self, creds: ProviderCredentials, flight_id: str) -> list[dict]:
        ...

    @abstractmethod
    def sync_media(self, creds: ProviderCredentials, since: str | None = None) -> list[dict]:
        ...

    def sync_docks(self, creds: ProviderCredentials) -> list[dict]:
        return []

    def sync_sensor_packages(self, creds: ProviderCredentials) -> list[dict]:
        return []

    def sync_attachments(self, creds: ProviderCredentials) -> list[dict]:
        return []

    def sync_users(self, creds: ProviderCredentials) -> list[dict]:
        return []
