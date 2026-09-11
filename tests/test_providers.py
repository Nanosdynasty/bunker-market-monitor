import pytest

from bunker_market.providers.base import ProviderError
from bunker_market.providers.bulugo import BulugoAdapter
from bunker_market.providers.oilprice import OilPriceAPIAdapter


class Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status
        self.ok = 200 <= status < 300

    def json(self):
        return self.payload


def test_bulugo_adapter_parses_documented_shape(monkeypatch):
    payload = {"data": [{
        "port": {"name": "Singapore", "country": "Singapore"},
        "fuel_type": "VLSFO",
        "price": {"value": 628.5, "currency": "USD", "unit": "MT", "last_updated": "2026-09-11T06:00:00Z"},
    }]}
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: Response(payload))
    rows = BulugoAdapter("secret", "https://example.test").fetch()
    assert len(rows) == 1
    assert rows[0].price == 628.5


def test_oilprice_adapter_accepts_wrapped_rows(monkeypatch):
    payload = {"data": {"prices": [{
        "port_name": "Rotterdam", "fuel_grade": "IFO380", "price": 501.25,
        "currency": "USD", "unit": "metric tonne", "as_of": "2026-09-11T05:00:00Z",
    }]}}
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: Response(payload))
    rows = OilPriceAPIAdapter("secret", "https://example.test").fetch()
    assert rows[0].grade == "HSFO"


@pytest.mark.parametrize("status,message", [(429, "rate limit"), (403, "not entitled")])
def test_provider_errors_are_clear(monkeypatch, status, message):
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: Response({}, status))
    with pytest.raises(ProviderError, match=message):
        BulugoAdapter("secret", "https://example.test").fetch()
