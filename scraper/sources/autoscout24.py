"""AutoScout24: alleen op expliciet verzoek (zie sources/__init__.py). Splitst op prijs, want
de site toont per zoekopdracht een beperkt aantal pagina's."""
from __future__ import annotations

import re

from ..parsing import (clean_text, make_listing, next_data, norm_body, norm_fuel, norm_plate,
                       norm_transmission, power_from_text, to_int)

ORIGIN = "https://www.autoscout24.nl"
SEARCH = f"{ORIGIN}/lst/bmw/x1?atype=C&cy=NL&ustate=U&sort=price&desc=0"
MAX_PAGES = 20
PAGE_SIZE = 19
PRICE_MAX = 150_000


def parse_listing(raw: dict) -> dict | None:
    vehicle = raw.get("vehicle") or {}
    if vehicle.get("model") != "X1" or vehicle.get("offerType") != "U":
        return None
    details = {d.get("iconName"): d.get("data") for d in raw.get("vehicleDetails") or []}
    tracking = raw.get("tracking") or {}
    price = raw.get("price") or {}
    location = raw.get("location") or {}
    seller = raw.get("seller") or {}
    first_reg = re.search(r"(\d{4})$", tracking.get("firstRegistration") or "")
    kw, hp = power_from_text(details.get("speedometer"))
    images = raw.get("images") or []
    is_dealer = seller.get("type") == "Dealer"
    return make_listing(
        "autoscout24", raw.get("id"), ORIGIN + (raw.get("url") or ""),
        title=clean_text(f"BMW X1 {vehicle.get('modelVersionInput') or ''}"),
        variant_text=vehicle.get("subtitle"),
        price_eur=price.get("priceRaw") or to_int(tracking.get("price")),
        catalog_price_eur=to_int(price.get("suggestedRetailPrice")),
        mileage_km=to_int(tracking.get("mileage")),
        year=int(first_reg.group(1)) if first_reg else None,
        fuel=norm_fuel(vehicle.get("fuel")),
        transmission=norm_transmission(vehicle.get("transmission")),
        body=norm_body(vehicle.get("bodyType")),
        power_kw=kw, power_hp=hp,
        engine_cc=to_int(vehicle.get("engineDisplacementInCCM")),
        license_plate=norm_plate(vehicle.get("licensePlate")),
        seller_type="Bedrijf" if is_dealer else "Particulier",
        seller_name=clean_text(seller.get("companyName")) if is_dealer else None,
        city=location.get("city"),
        image_url=images[0] if images else None,
    )


def parse_page(html: str) -> tuple[list[dict], int | None, int | None]:
    props = next_data(html) or {}
    items = [parse_listing(raw) for raw in props.get("listings") or []]
    return [i for i in items if i], props.get("numberOfResults"), props.get("numberOfPages")


def _crawl_range(fetcher, run, low: int, high: int) -> None:
    query = f"{SEARCH}&pricefrom={low}&priceto={high}"
    page = fetcher.get(query)
    if page is None:
        return
    items, total, pages = parse_page(page.text)
    run.add_all(items)
    total, pages = total or 0, pages or 1
    # Te veel voor de paginalimiet: halveer de prijsrange en probeer opnieuw.
    if total > MAX_PAGES * PAGE_SIZE and high - low > 100:
        middle = (low + high) // 2
        _crawl_range(fetcher, run, low, middle)
        _crawl_range(fetcher, run, middle + 1, high)
        return
    for number in range(2, min(pages, MAX_PAGES) + 1):
        next_page = fetcher.get(f"{query}&page={number}")
        if next_page is None:
            break
        items, _, _ = parse_page(next_page.text)
        if not items:
            break
        run.add_all(items)


def crawl(fetcher, run) -> None:
    first = fetcher.get(SEARCH)
    if first is None:
        run.note("Startpagina niet opgehaald (robots.txt of blokkade)")
        return
    items, total, _ = parse_page(first.text)
    run.expected = total
    run.add_all(items)
    _crawl_range(fetcher, run, 0, PRICE_MAX)
