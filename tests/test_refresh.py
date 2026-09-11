from datetime import datetime

from bunker_market.models import Observation, ProviderState, db
from bunker_market.providers.base import ProviderObservation
from bunker_market.refresh import perform_refresh


class WorkingAdapter:
    provider_id = "bulugo"
    display_name = "Bulugo"
    configured = True

    def fetch(self):
        return [ProviderObservation(
            port_name="Singapore", country="Singapore", region="Asia", grade="VLSFO",
            price=630.0, currency="USD", unit="MT", source_time=datetime(2026, 9, 11, 8),
            provenance_url="https://example.test", source_label="test",
        )]


class FailingAdapter:
    provider_id = "bulugo"
    display_name = "Bulugo"
    configured = True

    def fetch(self):
        from bunker_market.providers.base import ProviderError
        raise ProviderError("temporary upstream failure")


def test_refresh_inserts_then_retains_last_good_on_failure(app, monkeypatch):
    with app.app_context():
        state = db.session.get(ProviderState, "bulugo")
        state.configured = True
        state.daily_quota = 100
        state.next_allowed_at = None
        monkeypatch.setattr("bunker_market.refresh.build_adapters", lambda: [(WorkingAdapter(), 100)])
        result = perform_refresh(force=True)
        assert result["inserted"] == 1
        assert Observation.query.count() == 1

        state = db.session.get(ProviderState, "bulugo")
        state.next_allowed_at = None
        monkeypatch.setattr("bunker_market.refresh.build_adapters", lambda: [(FailingAdapter(), 100)])
        result = perform_refresh(force=True)
        assert result["status"] == "failed"
        assert Observation.query.count() == 1
        assert db.session.get(ProviderState, "bulugo").status == "unavailable"
