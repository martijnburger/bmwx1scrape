"""Marktplaats: paginering via /p/N/ is toegestaan; data staat in __NEXT_DATA__."""
from __future__ import annotations

import re

from ..parsing import (clean_text, make_listing, next_data, norm_body, norm_fuel, norm_transmission,
                       to_int)

BASE = "https://www.marktplaats.nl/l/auto-s/bmw/f/x1/622/"
MAX_NEW_KM = 100
BID_TYPES = ("MIN_BID", "FAST_BID")


def _attrs(listing: dict) -> dict:
    out = {}
    for attr in (listing.get("attributes") or []) + (listing.get("extendedAttributes") or []):
        out.setdefault(attr.get("key"), attr)
    return out


def parse_listing(raw: dict) -> dict | None:
    attrs = _attrs(raw)
    value = lambda key: (attrs.get(key) or {}).get("value")
    if value("model") and value("model") != "X1":
        return None
    condition = str(value("condition") or "").lower()
    mileage = to_int(value("mileage"))
    # Niet elke nieuwe auto heeft het label; zonder "gebruikt" telt een lege teller ook als nieuw.
    if condition == "nieuw" or (condition != "gebruikt" and mileage is not None and mileage <= MAX_NEW_KM):
        return None
    info = raw.get("priceInfo") or {}
    # Autobedrijven zetten hun prijs vaak bij "bieden vanaf"; dat bedrag is dus wel bruikbaar.
    price_type = info.get("priceType")
    cents = info.get("priceCents") if price_type in ("FIXED", *BID_TYPES) else None
    seller = raw.get("sellerInformation") or {}
    advertiser = value("advertiser")
    # Zonder expliciet veld wijst een bedrijfslogo op een bedrijf; anders blijft het onbekend.
    is_company = advertiser == "Bedrijf" or (advertiser is None and bool(seller.get("sellerLogoUrl")))
    seller_type = "Bedrijf" if is_company else ("Particulier" if advertiser else None)
    image = next(iter(raw.get("imageUrls") or []), None)
    title = clean_text(raw.get("title"))
    kw, hp = _power(raw.get("categorySpecificDescription") or raw.get("description"))
    return make_listing(
        "marktplaats", raw.get("itemId"), "https://www.marktplaats.nl" + (raw.get("vipUrl") or ""),
        title=title,
        price_eur=round(cents / 100) if cents else None,
        price_is_bid=price_type in BID_TYPES and bool(cents),
        mileage_km=mileage,
        year=to_int(value("constructionYear")),
        fuel=norm_fuel(value("fuel")),
        transmission=norm_transmission(value("transmission")),
        body=norm_body(value("body")),
        power_kw=kw, power_hp=hp,
        energy_label=value("energyLabel"),
        nap=True if raw.get("napAvailable") else None,
        seller_type=seller_type,
        # Namen van particulieren zijn persoonsgegevens en voor deze analyse niet nodig.
        seller_name=clean_text(seller.get("sellerName")) if is_company else None,
        city=(raw.get("location") or {}).get("cityName"),
        image_url="https:" + image if image and image.startswith("//") else image,
        options=(attrs.get("options") or {}).get("values") or [],
    )


def _power(text: str | None) -> tuple[int | None, int | None]:
    match = re.search(r"(\d{2,3})\s*kw\s*\((\d{2,3})\s*pk\)", text or "", re.I)
    return (int(match.group(1)), int(match.group(2))) if match else (None, None)


def parse_page(html: str) -> tuple[list[dict], int, int | None, int | None]:
    """Geeft (bruikbare advertenties, aantal overgeslagen, totaal volgens site, laatste pagina)."""
    props = next_data(html) or {}
    response = props.get("searchRequestAndResponse") or {}
    raw_items = response.get("listings") or []
    items = [i for i in map(parse_listing, raw_items) if i]
    return items, len(raw_items) - len(items), response.get("totalResultCount"), response.get("maxAllowedPageNumber")


def crawl(fetcher, run) -> None:
    page_number, last_page = 1, 1
    while page_number <= last_page:
        url = BASE if page_number == 1 else f"{BASE}p/{page_number}/"
        page = fetcher.get(url)
        if page is None:
            run.note(f"Pagina {page_number} niet opgehaald")
            page_number += 1
            continue
        items, skipped, total, max_page = parse_page(page.text)
        if not items and not skipped:
            # Een losse lege respons komt voor; opnieuw proberen en daarna doorgaan.
            page = fetcher.get(url)
            items, skipped, total, max_page = parse_page(page.text) if page else ([], 0, None, None)
            if not items and not skipped:
                run.note(f"Pagina {page_number} bleef leeg")
        if page_number == 1:
            run.expected = total
            last_page = max_page or 1
        run.skipped += skipped
        run.add_all(items)
        page_number += 1
