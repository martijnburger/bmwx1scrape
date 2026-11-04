"""Hulpfuncties om data uit pagina's te halen en waarden gelijk te trekken."""
from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any

DECODER = json.JSONDecoder()


def ld_json_blocks(html: str) -> list[Any]:
    blocks = []
    for raw in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            blocks.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return blocks


def item_list(html: str) -> dict | None:
    for block in ld_json_blocks(html):
        if isinstance(block, dict) and block.get("@type") == "ItemList":
            return block
    return None


def next_data(html: str) -> dict | None:
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(1)).get("props", {}).get("pageProps")
    except json.JSONDecodeError:
        return None


def flight_text(html: str) -> str:
    """Voegt de streaming-payload van Next.js (self.__next_f) samen tot één tekst."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html)
    out = []
    for chunk in chunks:
        try:
            out.append(json.loads(chunk))
        except json.JSONDecodeError:
            continue
    return "".join(out)


def to_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def power_from_text(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    kw = re.search(r"(\d{2,3})\s*kW", text, re.I)
    hp = re.search(r"(\d{2,3})\s*(?:PK|hp)\b", text, re.I)
    kw_value = int(kw.group(1)) if kw else None
    hp_value = int(hp.group(1)) if hp else None
    if kw_value and not hp_value:
        hp_value = round(kw_value * 1.35962)
    if hp_value and not kw_value:
        kw_value = round(hp_value / 1.35962)
    return kw_value, hp_value


def norm_fuel(value: str | None, plugin: bool = False) -> str | None:
    if not value:
        return None
    text = value.lower()
    if plugin or "plug" in text or "phev" in text:
        return "Plug-in hybride"
    if "hybrid" in text or ("elektr" in text and ("benz" in text or "dies" in text)):
        return "Hybride"
    if "elektr" in text:
        return "Elektrisch"
    if "benz" in text:
        return "Benzine"
    if "dies" in text:
        return "Diesel"
    if "lpg" in text:
        return "LPG"
    return "Overig"


def norm_transmission(value: str | None) -> str | None:
    if not value:
        return None
    text = value.lower()
    if "semi" in text:
        return "Semi-automaat"
    if "auto" in text:
        return "Automaat"
    if "hand" in text or "manu" in text:
        return "Handgeschakeld"
    return None


def norm_body(value: str | None) -> str | None:
    if not value:
        return None
    text = value.lower()
    if "suv" in text or "terrein" in text:
        return "SUV"
    if "mpv" in text:
        return "MPV"
    return value.strip().capitalize()


def norm_color(value: str | None) -> str | None:
    return value.strip().capitalize() if value and value.strip() else None


def norm_plate(value: str | None) -> str | None:
    if not value:
        return None
    plate = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    return plate if 5 <= len(plate) <= 8 else None


def clean_text(value: str | None) -> str | None:
    return html_lib.unescape(value).strip() if value else None


VARIANT = re.compile(r"\b([sx])\s?drive\s?(\d{2})\s?([a-z]{1,2})\b", re.I)
TRIMS = [
    (re.compile(r"\bM[\s-]?sport\b", re.I), "M Sport"),
    (re.compile(r"\bhigh[\s-]?executive\b", re.I), "High Executive"),
    (re.compile(r"\bx[\s-]?line\b", re.I), "xLine"),
    (re.compile(r"\bsport[\s-]?line\b", re.I), "Sport Line"),
    (re.compile(r"\bcentennial\b", re.I), "Centennial"),
    (re.compile(r"\bbusiness\b", re.I), "Business"),
    (re.compile(r"\bcorporate\b", re.I), "Corporate"),
    (re.compile(r"\bexecutive\b", re.I), "Executive"),
]


def parse_variant(*texts: str | None) -> dict[str, str | None]:
    """Motorvariant, aandrijving en uitvoeringslijn uit vrije tekst."""
    joined = " ".join(t for t in texts if t)
    result: dict[str, str | None] = {"variant": None, "drivetrain": None, "trim": None}
    match = VARIANT.search(joined)
    if match:
        prefix = match.group(1).lower()
        result["variant"] = f"{prefix}Drive{match.group(2)}{match.group(3).lower()}"
        result["drivetrain"] = f"{prefix}Drive"
    elif re.search(r"\bM35i\b", joined, re.I):
        result["variant"], result["drivetrain"] = "M35i", "xDrive"
    for pattern, label in TRIMS:
        if pattern.search(joined):
            result["trim"] = label
            break
    return result


def generation(year: int | None) -> str | None:
    """Benadering op basis van bouwjaar; de wisseljaren 2015 en 2022 overlappen in werkelijkheid."""
    if not year:
        return None
    if year <= 2015:
        return "E84 (2009-2015)"
    if year <= 2022:
        return "F48 (2015-2022)"
    return "U11 (2022-nu)"


MIN_REAL_PRICE = 500


def apply_rules(listing: dict) -> None:
    """Correcties die ook gelden voor eerder opgeslagen advertenties."""
    # Prijzen als € 1 zijn lokkertjes of "bel voor prijs", geen vraagprijs.
    if listing.get("price_eur") is not None and listing["price_eur"] < MIN_REAL_PRICE:
        listing["price_eur"] = None
    # Plaatshouders van sites zijn geen gegevens.
    if (listing.get("seller_name") or "").lower() == "onbekende dealer":
        listing["seller_name"] = None
    for key in ("power_hp", "power_kw"):
        if not listing.get(key):
            listing[key] = None
    # Sites labelen plug-ins wisselend (ook als benzine); de variantnaam (xDrive25e) is eenduidig.
    if (listing.get("variant") or "").endswith("e"):
        listing["fuel"] = "Plug-in hybride"


def make_listing(source: str, source_id: Any, url: str, **fields: Any) -> dict:
    listing = {
        "source": source, "source_id": str(source_id), "url": url,
        "title": None, "price_eur": None, "price_is_bid": False, "catalog_price_eur": None, "mileage_km": None,
        "year": None, "fuel": None, "transmission": None, "body": None, "color": None,
        "power_kw": None, "power_hp": None, "engine_cc": None, "doors": None,
        "energy_label": None, "license_plate": None, "nap": None, "seller_type": None,
        "seller_name": None, "city": None, "province": None, "image_url": None, "options": [],
    }
    listing.update(fields)
    listing.update(parse_variant(listing.get("title"), listing.get("variant_text")))
    listing.pop("variant_text", None)
    apply_rules(listing)
    if listing["city"]:
        listing["city"] = listing["city"].strip().title()
    return listing
