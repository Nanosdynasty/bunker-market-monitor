import math
import random
from datetime import timedelta

from .models import Observation, Port, ProviderState, db, utcnow
from .normalization import KNOWN_PORTS


DEMO_PORTS = [
    "Singapore",
    "Rotterdam",
    "Fujairah",
    "Houston",
    "Gibraltar",
    "Antwerp",
    "Los Angeles",
    "Panama Balboa",
    "Busan",
    "Hong Kong",
    "Shanghai",
    "Malta",
    "Algeciras",
    "Durban",
    "New York",
]

BASE_PRICES = {"VLSFO": 625.0, "HSFO": 515.0, "MGO": 805.0}


def seed_demo_data() -> None:
    repaired = Observation.query.filter_by(
        provenance_url="demo://generated", synthetic=False
    ).update({"synthetic": True}, synchronize_session=False)
    if Observation.query.first():
        if repaired:
            db.session.commit()
        return
    random.seed(20260911)
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    providers = []
    for provider_id, name, quota in (
        ("bulugo", "Bulugo", 100),
        ("oilpriceapi", "OilPriceAPI", 50),
    ):
        provider = db.session.get(ProviderState, provider_id)
        if not provider:
            provider = ProviderState(id=provider_id, name=name)
            db.session.add(provider)
        provider.configured = False
        provider.status = "demo"
        provider.daily_quota = quota
        provider.last_success_at = now
        provider.records_last_run = 45
        provider.ports_last_run = 15
        providers.append(provider)

    for port_index, name in enumerate(DEMO_PORTS):
        code, country, region, priority = KNOWN_PORTS[name.lower()]
        db.session.add(
            Port(code=code, name=name, country=country, region=region, priority=priority)
        )
        for provider_index, provider in enumerate(providers):
            for grade_index, (grade, base) in enumerate(BASE_PRICES.items()):
                port_adjustment = (port_index - 7) * 3.8
                provider_adjustment = provider_index * -4.5
                for step in range(56):
                    timestamp = now - timedelta(hours=(55 - step) * 6)
                    wave = math.sin((step + port_index) / 5) * 7
                    drift = step * 0.12
                    noise = random.uniform(-2.2, 2.2)
                    price = base + port_adjustment + provider_adjustment + wave + drift + noise
                    db.session.add(
                        Observation(
                            provider_id=provider.id,
                            port_code=code,
                            grade=grade,
                            price=round(price, 2),
                            source_time=timestamp,
                            retrieved_at=timestamp,
                            provenance_url="demo://generated",
                            source_label=f"{provider.name} demo fixture",
                            synthetic=True,
                        )
                    )
    db.session.commit()
