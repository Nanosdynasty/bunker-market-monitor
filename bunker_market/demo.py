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
    # No synthetic prices: the product displays only the connected workbook.
    return None
