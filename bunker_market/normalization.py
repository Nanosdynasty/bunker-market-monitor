import re
from datetime import datetime, timezone
from typing import Any


GRADE_ALIASES = {
    "VLSFO": "VLSFO",
    "LSFO": "VLSFO",
    "0.5%": "VLSFO",
    "HSFO": "HSFO",
    "HFO380": "HSFO",
    "IFO380": "HSFO",
    "IFO 380": "HSFO",
    "MGO": "MGO",
    "LSMGO": "MGO",
    "DMA": "MGO",
}

KNOWN_PORTS = {
    "singapore": ("SGSIN", "Singapore", "Asia", 1),
    "rotterdam": ("NLRTM", "Netherlands", "Europe", 2),
    "fujairah": ("AEFJR", "United Arab Emirates", "Middle East", 3),
    "houston": ("USHOU", "United States", "Americas", 4),
    "gibraltar": ("GIGIB", "Gibraltar", "Europe", 5),
    "antwerp": ("BEANR", "Belgium", "Europe", 6),
    "los angeles": ("USLAX", "United States", "Americas", 7),
    "panama balboa": ("PABLB", "Panama", "Americas", 8),
    "balboa": ("PABLB", "Panama", "Americas", 8),
    "busan": ("KRPUS", "South Korea", "Asia", 9),
    "hong kong": ("HKHKG", "Hong Kong", "Asia", 10),
    "shanghai": ("CNSHA", "China", "Asia", 11),
    "malta": ("MTMLA", "Malta", "Europe", 12),
    "algeciras": ("ESALG", "Spain", "Europe", 13),
    "durban": ("ZADUR", "South Africa", "Africa", 14),
    "new york": ("USNYC", "United States", "Americas", 15),
    "ghent": ("BEGNE", "Belgium", "Europe", 16),
    "hamburg": ("DEHAM", "Germany", "Europe", 17),
    "skaw": ("DKSKA", "Denmark", "Europe", 18),
    "tallinn": ("EETLL", "Estonia", "Europe", 19),
}


def parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, (int, float)):
        result = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            result = datetime.fromisoformat(text)
        except ValueError:
            return datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    if result.tzinfo:
        result = result.astimezone(timezone.utc).replace(tzinfo=None)
    return result


def canonical_grade(value: Any) -> str | None:
    text = re.sub(r"[_-]+", " ", str(value or "").strip().upper())
    compact = text.replace(" ", "")
    return GRADE_ALIASES.get(text) or GRADE_ALIASES.get(compact)


def canonical_unit(value: Any) -> str | None:
    text = str(value or "MT").strip().upper().replace("/", "")
    if text in {"MT", "TONNE", "TONNES", "METRICTON", "METRICTONNE"}:
        return "MT"
    if "METRIC" in text and "TON" in text:
        return "MT"
    return None


def port_identity(name: str, country: str = "", region: str = "") -> dict[str, Any]:
    cleaned = re.sub(r"\s+", " ", name.strip())
    known = KNOWN_PORTS.get(cleaned.lower())
    if known:
        code, known_country, known_region, priority = known
        return {
            "code": code,
            "name": cleaned.title() if cleaned.lower() != "hong kong" else "Hong Kong",
            "country": country or known_country,
            "region": region or known_region,
            "priority": priority,
        }
    slug = re.sub(r"[^A-Z0-9]", "", cleaned.upper())[:9]
    return {
        "code": f"X{slug}" or "XUNKNOWN",
        "name": cleaned or "Unknown",
        "country": country or "Unknown",
        "region": region or "Other",
        "priority": 999,
    }


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) is not None:
            return row[key]
    return None


def normalize_provider_row(
    row: dict[str, Any], *, provenance_url: str, source_label: str, nested_price: bool
) -> dict[str, Any] | None:
    port_value = _first(row, "port", "port_name", "location", "market")
    if isinstance(port_value, dict):
        port_name = str(_first(port_value, "name", "port", "title") or "")
        country = str(_first(port_value, "country", "country_name") or "")
        region = str(_first(port_value, "region") or "")
    else:
        port_name = str(port_value or "")
        country = str(_first(row, "country", "country_name") or "")
        region = str(_first(row, "region") or "")

    grade = canonical_grade(_first(row, "fuel_type", "fuel_grade", "grade", "product"))
    price_node = row.get("price")
    if nested_price and isinstance(price_node, dict):
        raw_price = _first(price_node, "value", "price", "amount")
        currency = str(_first(price_node, "currency") or "USD").upper()
        unit = canonical_unit(_first(price_node, "unit") or "MT")
        time_value = _first(price_node, "last_updated", "as_of", "timestamp")
    else:
        raw_price = (
            _first(price_node, "value", "amount")
            if isinstance(price_node, dict)
            else _first(row, "price", "value", "price_usd_mt", "price_indication_usd_mt")
        )
        currency = str(_first(row, "currency") or "USD").upper()
        unit = canonical_unit(_first(row, "unit", "price_unit") or "MT")
        time_value = _first(
            row, "as_of", "source_timestamp", "last_updated", "timestamp", "created_at"
        )

    try:
        price = float(raw_price)
    except (TypeError, ValueError):
        return None
    if not port_name or not grade or price <= 0 or currency != "USD" or unit != "MT":
        return None

    return {
        "port_name": port_name,
        "country": country,
        "region": region,
        "grade": grade,
        "price": price,
        "currency": "USD",
        "unit": "MT",
        "source_time": parse_time(time_value),
        "provenance_url": provenance_url,
        "source_label": source_label,
        "stale_upstream": bool(row.get("stale") or row.get("data_status") == "stale"),
        "synthetic": bool(row.get("synthetic")),
    }
