from .base import ProviderAdapter, ProviderError, ProviderObservation, rows_from_payload
from ..normalization import normalize_provider_row


class BulugoAdapter(ProviderAdapter):
    provider_id = "bulugo"
    display_name = "Bulugo"

    def fetch(self) -> list[ProviderObservation]:
        payload = self._request(
            headers={"Authorization": f"Bearer {self.api_key}"},
            params={"limit": 500},
        )
        observations = []
        for row in rows_from_payload(payload):
            item = normalize_provider_row(
                row,
                provenance_url=self.url,
                source_label="Bulugo",
                nested_price=True,
            )
            if item:
                observations.append(ProviderObservation(**item))
        if not observations:
            raise ProviderError("Bulugo returned no supported USD/MT bunker observations")
        return observations
