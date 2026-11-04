"""AutoTrack: paginering (?pageNumber) is uitgesloten, maar de sitemap noemt filterpagina's per plaats."""
from __future__ import annotations

import json
import re

from ..details import enrich
from ..parsing import (DECODER, clean_text, flight_text, item_list, make_listing, norm_body, norm_color,
                       norm_fuel, norm_plate, norm_transmission, to_int)

ORIGIN = "https://www.autotrack.nl"
BASE_PATH = "/aanbod/merk/bmw/model/x1"
SITEMAPS = [f"{ORIGIN}/sitemap_aanbod_{n}.xml" for n in (1, 2)]
ANCHOR = '{"beschikbaarheidsStatus"'
OPTIONS_ANCHOR = '"options":[{"categoryName"'


def parse_ad(raw: dict) -> dict | None:
    data = raw.get("autogegevens") or {}
    general = data.get("algemeen") or {}
    if general.get("modelnaam") != "X1" or raw.get("soortAuto") != "OCCASION":
        return None
    motor = data.get("motor") or {}
    history = data.get("geschiedenis") or {}
    seller = (raw.get("aanbieder") or {}).get("aanbiedergegevens") or {}
    ad_id = raw.get("advertentieId")
    photos = (raw.get("media") or {}).get("photos") or []
    year = to_int(history.get("bouwjaar"))
    version = clean_text(general.get("commercieleUitvoering") or general.get("uitvoering"))
    return make_listing(
        "autotrack", ad_id,
        (raw.get("url") or f"{ORIGIN}/a/bmw-x1-{general.get('brandstofsoortSlug', 'auto')}-{year}-{ad_id}").split("?")[0],
        title=f"BMW X1 {version}" if version else "BMW X1",
        price_eur=to_int((raw.get("prijs") or {}).get("totaalInclusiefBtw")),
        catalog_price_eur=to_int(history.get("catalogusprijs")),
        mileage_km=to_int(history.get("kilometerstand")),
        year=year,
        fuel=norm_fuel(general.get("brandstofsoort")),
        transmission=norm_transmission(general.get("transmissietype")),
        body=norm_body(general.get("carrosserievorm")),
        color=norm_color(general.get("kleur")),
        power_kw=to_int(motor.get("vermogenKw")),
        power_hp=to_int(motor.get("vermogenPk")),
        engine_cc=to_int(motor.get("motorinhoud")),
        doors=general.get("aantalDeuren"),
        energy_label=(data.get("milieu") or {}).get("energielabel"),
        license_plate=norm_plate(raw.get("kenteken")),
        nap=True if history.get("kilometerstandCorrect") else None,
        seller_type="Bedrijf",
        seller_name=clean_text(seller.get("naam")),
        city=seller.get("plaatsnaam"),
        province=seller.get("provincie"),
        image_url=f"https://cdn.autotrack.nl/{photos[0]}?h=675&w=900" if photos else None,
    )


def parse_page(html: str) -> tuple[list[dict], int | None]:
    text = flight_text(html)
    ads: dict[str, dict] = {}
    position = text.find(ANCHOR)
    while position >= 0:
        try:
            raw, length = DECODER.raw_decode(text[position:])
        except json.JSONDecodeError:
            position = text.find(ANCHOR, position + 1)
            continue
        listing = parse_ad(raw)
        if listing:
            ads[listing["source_id"]] = listing
        position = text.find(ANCHOR, position + length)
    listing_block = item_list(html) or {}
    return list(ads.values()), to_int(listing_block.get("numberOfItems"))


def parse_detail(html: str) -> list[str]:
    """Opties staan per categorie; een groep als "Dak" noemt de echte opties als suboptions."""
    text = flight_text(html)
    index = text.find(OPTIONS_ANCHOR)
    if index < 0:
        return []
    try:
        categories, _ = DECODER.raw_decode(text[index + len('"options":'):])
    except json.JSONDecodeError:
        return []
    options: list[str] = []
    for category in categories:
        for option in category.get("options") or []:
            options += option.get("suboptions") or [option.get("name")]
    return list(dict.fromkeys(o for o in options if o))


def slices_from_sitemap(xml: str) -> list[str]:
    pattern = re.compile(r"<loc>(" + re.escape(ORIGIN + BASE_PATH) + r"(?:/[^<]*)?)</loc>")
    return pattern.findall(xml)


def _priority(url: str) -> int:
    """Plaatsen zijn het fijnst en leveren dus de meeste unieke advertenties per verzoek."""
    if "plaatsnaam" in url:
        return 0
    if "provincie" in url:
        return 1
    return 2


def crawl(fetcher, run) -> None:
    urls: list[str] = []
    for sitemap in SITEMAPS:
        page = fetcher.get(sitemap)
        if page:
            urls += slices_from_sitemap(page.text)

    first = fetcher.get(ORIGIN + BASE_PATH)
    if first is None:
        run.note("Startpagina niet opgehaald")
        return
    items, total = parse_page(first.text)
    run.expected = total
    run.add_all(items)

    for url in sorted(set(urls), key=_priority):
        if total and run.count >= total:
            break
        page = fetcher.get(url)
        if page is None or BASE_PATH not in page.url:  # verwijzing weg van het X1-filter
            continue
        items, _ = parse_page(page.text)
        run.add_all(items)

    enrich(fetcher, run, parse_detail)
