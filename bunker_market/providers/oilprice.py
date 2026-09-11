from .base import ProviderAdapter, ProviderError, ProviderObservation, rows_from_payload
from ..normalization import normalize_provider_row


class OilPriceAPIAdapter(ProviderAdapter):
    provider_id = "oilpriceapi"
    display_name = "OilPriceAPI"

    def fetch(self) -> list[ProviderObservation]:
        payload = self._request(
            headers={"Authorization": f"Token {self.api_key}"},
        )
        observations = []
        for row in rows_from_payload(payload):
            item = normalize_provider_row(
                row,
                provenance_url=self.url,
                source_label=str(row.get("source") or "OilPriceAPI"),
                nested_price=False,
            )
            if item:
                observations.append(ProviderObservation(**item))
        if not observations:
            raise ProviderError(
                "OilPriceAPI returned no supported bunker observations; check dataset entitlement"
            )
        return observations
