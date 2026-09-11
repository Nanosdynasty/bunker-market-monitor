from bunker_market.normalization import canonical_grade, canonical_unit, normalize_provider_row, port_identity


def test_grade_and_unit_aliases():
    assert canonical_grade("IFO 380") == "HSFO"
    assert canonical_grade("lsmgo") == "MGO"
    assert canonical_grade("VLSFO") == "VLSFO"
    assert canonical_grade("unknown") is None
    assert canonical_unit("metric tonne") == "MT"
    assert canonical_unit("barrel") is None


def test_bulugo_nested_price_normalization():
    row = {
        "port": {"name": "Singapore", "country": "Singapore"},
        "fuel_type": "VLSFO",
        "price": {
            "value": 628.5,
            "currency": "USD",
            "unit": "MT",
            "last_updated": "2026-09-11T06:00:00Z",
        },
    }
    value = normalize_provider_row(
        row, provenance_url="https://example.test", source_label="Bulugo", nested_price=True
    )
    assert value["price"] == 628.5
    assert value["grade"] == "VLSFO"
    assert value["source_time"].hour == 6


def test_rejects_wrong_currency_or_unit():
    base = {"port": "Singapore", "grade": "MGO", "price": 900}
    assert normalize_provider_row(
        {**base, "currency": "EUR"}, provenance_url="x", source_label="x", nested_price=False
    ) is None
    assert normalize_provider_row(
        {**base, "unit": "barrel"}, provenance_url="x", source_label="x", nested_price=False
    ) is None


def test_known_and_unknown_port_identity():
    assert port_identity("Rotterdam")["code"] == "NLRTM"
    assert port_identity("Example Harbour")["code"].startswith("X")
