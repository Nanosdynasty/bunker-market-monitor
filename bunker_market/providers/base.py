from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

import requests


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ProviderObservation:
    port_name: str
    country: str
    region: str
    grade: str
    price: float
    currency: str
    unit: str
    source_time: datetime
    provenance_url: str
    source_label: str
    stale_upstream: bool = False
    synthetic: bool = False


class ProviderAdapter:
    provider_id = "base"
    display_name = "Base provider"

    def __init__(self, api_key: str, url: str, timeout: int = 15):
        self.api_key = api_key
        self.url = url
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())

    def fetch(self) -> list[ProviderObservation]:
        raise NotImplementedError

    def _request(self, *, headers: dict[str, str], params: dict[str, Any] | None = None):
        try:
            response = requests.get(
                self.url, headers=headers, params=params, timeout=self.timeout
            )
        except requests.Timeout as exc:
            raise ProviderError(f"{self.display_name} timed out") from exc
        except requests.RequestException as exc:
            raise ProviderError(f"{self.display_name} connection failed") from exc

        if response.status_code == 429:
            raise ProviderError(
                f"{self.display_name} rate limit reached", status_code=429
            )
        if response.status_code in {401, 403}:
            raise ProviderError(
                f"{self.display_name} key is invalid or not entitled to bunker data",
                status_code=response.status_code,
            )
        if not response.ok:
            raise ProviderError(
                f"{self.display_name} returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(f"{self.display_name} returned invalid JSON") from exc


def rows_from_payload(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "prices", "results", "rows", "bunker_fuels", "items", "ports"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            nested = rows_from_payload(value)
            if nested:
                return nested
    return []
