"""Herkent dure opties in optielijsten en advertentietitels, onder één naam per optie."""
from __future__ import annotations

import re

FEATURES = {
    "Achteruitrijcamera": r"achteruitrijcamera|parkeercamera|360\s?°?\s?camera|\bcamera\b|parking assist\w* plus",
    "360° camera": r"360\s?°?\s?camera|surround view|parking assist\w* plus",
    "Adaptive cruise control": r"ada?ptie?ve? cruise|active cruise|\bacc\b|driving assist\w* (?:plus|prof)",
    "Head-up display": r"head[\s-]?up|\bhud\b",
    "Panorama-/schuifdak": r"\bpano|schuif|open dak|dakraam",
    "Trekhaak": r"trekhaak",
    "Leder": r"\bleder(?:en)?\b(?!\s*(?:stuur|pook))|(?<!stuurwiel )\bleer\b",
    "Elektrische stoelen": r"elek\w*\.?\s*(?:voor)?stoel|stoelverstelling|\bmemory\b",
    "Stoelverwarming": r"stoelverwarming",
    "Stuurwielverwarming": r"stuur(?:wiel)?verwarming",
    "Elektrische achterklep": r"elek\w*\.?[\s-]*(?:a-klep|achterklep|klep)",
    "Keyless entry": r"keyless|comfort access",
    "Harman Kardon/soundsysteem": r"harman|sound system",
    "Adaptieve/laser-koplampen": r"adaptieve? (?:led|lichten|koplamp)|laserlicht",
    "Dodehoekdetectie": r"dode\s?hoek|blind spot",
    "Apple CarPlay": r"car\s?play",
    "Draadloos laden": r"inductie|draadloos laden|wireless charging",
    "Standkachel": r"standkachel",
    "M Sport": r"\bm[\s/-]?sport",
}
_COMPILED = {name: re.compile(pattern, re.I) for name, pattern in FEATURES.items()}
_NEGATION = re.compile(r"\b(?:geen|zonder)\s+\S+", re.I)


# Uitvoeringslijnen staan niet in optielijsten; de naam komt altijd uit de advertentietekst.
_FROM_TEXT_ALWAYS = {"M Sport"}


def _detect(texts: list[str], names) -> list[str]:
    text = _NEGATION.sub(" ", " | ".join(texts))
    return [name for name in names if _COMPILED[name].search(text)]


def detect_features(options: list[str], titles: list[str]) -> tuple[list[str], str | None]:
    """Geeft (opties, herkomst). De titel is alleen het laatste redmiddel: is er een optielijst,
    dan telt die, ook als de titel meer belooft."""
    if options:
        names = [n for n in FEATURES if n not in _FROM_TEXT_ALWAYS]
        found = set(_detect(options, names)) | set(_detect(titles, _FROM_TEXT_ALWAYS))
        return [n for n in FEATURES if n in found], "optielijst"
    found = _detect(titles, FEATURES)
    return found, "titel" if found else None
