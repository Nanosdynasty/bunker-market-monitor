from datetime import timedelta

from bunker_market.models import Observation, Port, ProviderState, db, utcnow
from bunker_market.demo import seed_demo_data


def seed_small(app):
    with app.app_context():
        now = utcnow()
        db.session.add(Port(code="SGSIN", name="Singapore", country="Singapore", region="Asia", priority=1))
        for provider_id, name in (("bulugo", "Bulugo"), ("oilpriceapi", "OilPriceAPI")):
            state = db.session.get(ProviderState, provider_id)
            state.name = name
            state.status = "current"
            state.configured = True
            state.last_success_at = now
            for offset, price in ((1, 620), (0, 625 if provider_id == "bulugo" else 622)):
                db.session.add(Observation(
                    provider_id=provider_id, port_code="SGSIN", grade="VLSFO", price=price,
                    source_time=now - timedelta(hours=offset), retrieved_at=now,
                    provenance_url="https://example.test", source_label=name,
                ))
        db.session.commit()


def test_health_and_readiness(client):
    assert client.get("/health").status_code == 200
    assert client.get("/ready").json["status"] == "ready"


def test_dashboard_comparison_and_sources(app, client):
    seed_small(app)
    dashboard = client.get("/api/dashboard?port=SGSIN&grade=VLSFO&range=7D").json
    assert dashboard["selectedPort"]["code"] == "SGSIN"
    assert dashboard["ports"][0]["grades"][0]["providers"]["bulugo"]["delta"] == 5
    comparison = client.get("/api/compare?grades=VLSFO").json
    assert comparison["rows"][0]["spread"] == 3
    sources = client.get("/api/sources").json
    assert len(sources["preview"]) == 4


def test_refresh_requires_csrf(client):
    assert client.post("/api/refresh").status_code == 403
    page = client.get("/")
    assert page.status_code == 200
    with client.session_transaction() as session:
        token = session["csrf_token"]
    response = client.post("/api/refresh", headers={"X-CSRF-Token": token})
    assert response.status_code == 200
    assert response.json["providers"][0]["status"] == "not_configured"


def test_html_contains_required_tabs_and_accessible_chart(client):
    html = client.get("/").get_data(as_text=True)
    assert "Dashboard" in html and "Compare" in html and "Sources" in html
    assert 'id="price-chart"' in html
    assert "Hover, tap, or focus" in html
    assert "Upload an Excel price file" in html


def test_demo_rows_remain_truthfully_labelled(app, client):
    with app.app_context():
        seed_demo_data()
        assert Observation.query.filter_by(synthetic=True).count() > 0
    assert client.get("/api/dashboard").json["mode"] == "demo"
