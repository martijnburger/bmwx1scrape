"""Gaspedaal: paginering is uitgesloten; 100 auto's per filterpagina in schema.org-data."""
from __future__ import annotations

import re

from ..parsing import (clean_text, item_list, make_listing, norm_body, norm_color, norm_fuel,
                       norm_transmission, power_from_text, to_int)

ORIGIN = "https://www.gaspedaal.nl"
BASE = f"{ORIGIN}/bmw/x1"


def parse_item(item: dict) -> dict | None:
    if item.get("model") != "X1" or "UsedCondition" not in str(item.get("itemCondition")):
        return None
    identifier = str(item.get("@id") or "")
    if "#" not in identifier:
        return None
    offer = item.get("offers") or {}
    seller = offer.get("seller") or {}
    address = seller.get("address") or {}
    config = item.get("vehicleConfiguration") or ""
    kw, hp = power_from_text(config)
    cc = re.search(r"(\d{3,4})\s*cc", config)
    return make_listing(
        "gaspedaal", identifier.split("#", 1)[1], identifier,
        title=clean_text(item.get("name")),
        price_eur=to_int(offer.get("price")),
        mileage_km=to_int((item.get("mileageFromOdometer") or {}).get("value")),
        year=to_int(item.get("vehicleModelDate") or item.get("productionDate")),
        fuel=norm_fuel(item.get("fuelType")),
        transmission=norm_transmission(item.get("vehicleTransmission")),
        body=norm_body(item.get("bodyType")),
        color=norm_color(item.get("color")),
        power_kw=kw, power_hp=hp,
        engine_cc=int(cc.group(1)) if cc else None,
        doors=item.get("numberOfDoors"),
        seller_type="Bedrijf" if seller.get("@type") == "AutoDealer" else None,
        seller_name=clean_text(seller.get("name")) if seller.get("@type") == "AutoDealer" else None,
        city=address.get("addressLocality"),
        province=address.get("addressRegion"),
        image_url=item.get("image"),
    )


def parse_page(html: str) -> tuple[list[dict], int | None]:
    block = item_list(html) or {}
    items = [parse_item((row or {}).get("item") or {}) for row in block.get("itemListElement") or []]
    return [i for i in items if i], to_int(block.get("numberOfItems"))


def facet_paths(html: str) -> list[str]:
    return sorted(set(re.findall(r'href="(/bmw/x1/[^"?#/]+)"', html)))


def crawl(fetcher, run) -> None:
    first = fetcher.get(BASE)
    if first is None:
        run.note("Startpagina niet opgehaald")
        return
    items, total = parse_page(first.text)
    run.expected = total
    run.add_all(items)
    # Bouwjaren eerst: die overlappen het minst.
    paths = sorted(facet_paths(first.text), key=lambda p: (not p.rsplit("/", 1)[1].isdigit(), p))
    for path in paths:
        if total and run.count >= total:
            break
        page = fetcher.get(ORIGIN + path)
        if page is None:
            continue
        items, _ = parse_page(page.text)
        run.add_all(items)
