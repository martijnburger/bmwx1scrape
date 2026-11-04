"""viaBOVAG: paginering is uitgesloten in robots.txt, dus we splitsen op filterpaden."""
from __future__ import annotations

import json

from ..details import enrich
from ..parsing import (DECODER, clean_text, flight_text, make_listing, norm_body, norm_color,
                       norm_fuel, norm_plate, norm_transmission, to_int)

BASE = "https://www.viabovag.nl/auto/merk-bmw/model-x1"
PAGE_SIZE = 25
FIRST_YEAR, YEARS_AHEAD = 2009, 2027

FACETS = [
    ["benzine", "diesel", "hybride", "elektrisch"],
    ["zwart", "wit", "grijs", "blauw", "zilver", "rood", "groen", "bruin", "beige", "geel", "oranje", "overig"],
    ["automatisch", "handgeschakeld", "semiautomatisch"],
]


def parse_listing(raw: dict) -> dict | None:
    vehicle = raw.get("vehicle") or {}
    if vehicle.get("model") != "X1" or vehicle.get("condition") != "Occasion":
        return None
    company = raw.get("company") or {}
    hp = to_int(vehicle.get("enginePower"))
    return make_listing(
        "viabovag", raw.get("id"), raw.get("url"),
        title=clean_text(raw.get("title")),
        variant_text=vehicle.get("commercialVersion"),
        price_eur=to_int(raw.get("price")),
        mileage_km=to_int(vehicle.get("mileage")),
        year=to_int(vehicle.get("year")),
        fuel=norm_fuel(vehicle.get("fuelType"), plugin=bool(vehicle.get("isPluginHybride"))),
        transmission=norm_transmission(vehicle.get("transmissionType")),
        body=norm_body(vehicle.get("bodyType")),
        color=norm_color(vehicle.get("color")),
        power_hp=hp,
        power_kw=round(hp / 1.35962) if hp else None,
        doors=vehicle.get("doors"),
        energy_label=vehicle.get("energyLabel"),
        license_plate=norm_plate(vehicle.get("licensePlate")),
        nap=True if vehicle.get("hasNapWeblabel") else None,
        seller_type="Bedrijf",
        seller_name=clean_text(company.get("name")),
        city=company.get("city"),
        image_url=raw.get("imageUrl"),
    )


def parse_page(html: str) -> tuple[list[dict], int | None]:
    text = flight_text(html)
    marker = '"searchResults":{"results":'
    index = text.find(marker)
    if index < 0:
        return [], None
    try:
        data, _ = DECODER.raw_decode(text[index + len('"searchResults":'):])
    except json.JSONDecodeError:
        return [], None
    items = [parse_listing(raw) for raw in data.get("results") or []]
    return [i for i in items if i], data.get("count")


def parse_detail(html: str) -> list[str]:
    text = flight_text(html)
    index = text.find('"accessories":[')
    if index < 0:
        return []
    try:
        accessories, _ = DECODER.raw_decode(text[index + len('"accessories":'):])
    except json.JSONDecodeError:
        return []
    return list(dict.fromkeys(a["formattedValue"] for a in accessories if a.get("hasValue") and a.get("formattedValue")))


def _split(fetcher, run, path: str, facet_index: int) -> None:
    page = fetcher.get(BASE + path)
    if page is None:
        return
    items, count = parse_page(page.text)
    run.add_all(items)
    if not count or count <= PAGE_SIZE:
        return
    if facet_index >= len(FACETS):
        run.missed(count - len(items), f"viaBOVAG-filter {path} is niet verder te splitsen")
        return
    for value in FACETS[facet_index]:
        _split(fetcher, run, f"{path}/{value}", facet_index + 1)


def crawl(fetcher, run) -> None:
    page = fetcher.get(f"{BASE}/occasion")
    if page is None:
        run.note("Startpagina niet opgehaald")
        return
    items, count = parse_page(page.text)
    run.expected = count
    run.add_all(items)
    for year in range(FIRST_YEAR, YEARS_AHEAD + 1):
        _split(fetcher, run, f"/occasion/bouwjaar-vanaf-{year}/bouwjaar-tot-en-met-{year}", 0)
    enrich(fetcher, run, parse_detail)
