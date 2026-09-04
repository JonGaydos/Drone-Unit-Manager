from app.integrations.base import DroneProvider

_PROVIDERS: dict[str, type[DroneProvider]] = {}


def register_provider(provider_class: type[DroneProvider]):
    _PROVIDERS[provider_class.PROVIDER_NAME] = provider_class
    return provider_class


def get_provider(name: str) -> DroneProvider:
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown provider: {name}. Available: {list(_PROVIDERS.keys())}")
    return _PROVIDERS[name]()


def list_providers() -> list[str]:
    return list(_PROVIDERS.keys())
