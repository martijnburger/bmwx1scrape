"""Voegt advertenties van alle sites samen tot één record per auto."""
from __future__ import annotations

from .features import detect_features
from .parsing import apply_rules, generation

MIN_SOFT_KM = 1000

SHARED_FIELDS = ["title", "catalog_price_eur", "mileage_km", "year", "fuel", "transmission", "body", "color",
                 "power_kw", "power_hp", "engine_cc", "doors", "energy_label", "license_plate", "nap",
                 "seller_type", "seller_name", "city", "province", "image_url", "variant", "drivetrain", "trim"]
# Meest volledige titels/gegevens eerst.
SOURCE_PRIORITY = {"viabovag": 0, "autotrack": 1, "autoscout24": 2, "gaspedaal": 3, "marktplaats": 4}


def _soft_keys(listing: dict) -> list[tuple]:
    """Herkenning zonder kenteken. De km-stand alleen is niet genoeg: dealers geven demo-auto's
    dezelfde standaardstand (2.500, 6.999 km), dus er moet een prijs of plaats bij kloppen."""
    year, km, price, city = (listing.get(k) for k in ("year", "mileage_km", "price_eur", "city"))
    if not (year and km and km >= MIN_SOFT_KM):
        return []
    keys = []
    if price:
        keys.append(("km-price", year, km, price))
    if city and km % 1000:
        keys.append(("km-city", year, km, city.lower()))
    return keys


def merge_listings(listings: list[dict]) -> list[dict]:
    for listing in listings:
        apply_rules(listing)

    parent = list(range(len(listings)))
    plates = {i: l.get("license_plate") for i, l in enumerate(listings)}
    sites = {i: {l["source"]} for i, l in enumerate(listings)}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int, soft: bool) -> None:
        a, b = find(a), find(b)
        if a == b or (plates[a] and plates[b] and plates[a] != plates[b]):
            return  # twee verschillende kentekens zijn nooit dezelfde auto
        if soft and sites[a] & sites[b]:
            return  # een site toont dezelfde auto zelden twee keer; eerder twee gelijke auto's
        parent[b] = a
        plates[a] = plates[a] or plates[b]
        sites[a] |= sites[b]

    # Eerst kentekens, want die zijn zeker; daarna de zachte kenmerken.
    first_seen: dict[tuple, int] = {}
    for index, listing in enumerate(listings):
        if listing.get("license_plate"):
            union(first_seen.setdefault(("plate", listing["license_plate"]), index), index, soft=False)
    for index, listing in enumerate(listings):
        for key in _soft_keys(listing):
            union(first_seen.setdefault(key, index), index, soft=True)

    groups: dict[int, list[dict]] = {}
    for index, listing in enumerate(listings):
        groups.setdefault(find(index), []).append(listing)

    cities = {}
    for listing in listings:
        if listing.get("city") and listing.get("province"):
            cities.setdefault(listing["city"].lower(), listing["province"])

    cars = []
    for group in groups.values():
        group.sort(key=lambda l: SOURCE_PRIORITY.get(l["source"], 9))
        car: dict = {"id": f"{group[0]['source']}:{group[0]['source_id']}"}
        for field in SHARED_FIELDS:
            car[field] = next((l[field] for l in group if l.get(field) not in (None, "")), None)
        car["options"] = list(dict.fromkeys(o for l in group for o in l.get("options") or []))
        car["features"], car["features_source"] = detect_features(car["options"], [l["title"] for l in group if l.get("title")])
        prices = [l["price_eur"] for l in group if l.get("price_eur")]
        car["price_eur"] = min(prices) if prices else None
        car["sources"] = [{"site": l["source"], "url": l["url"], "price_eur": l.get("price_eur"),
                           "price_is_bid": bool(l.get("price_is_bid"))} for l in group]
        if not car["province"] and car["city"]:
            car["province"] = cities.get(car["city"].lower())
        car["generation"] = generation(car["year"])
        cars.append(car)
    cars.sort(key=lambda c: (c["price_eur"] is None, c["price_eur"] or 0))
    return cars

