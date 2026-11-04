"""Herkent dure opties in optielijsten en advertentietitels, onder één naam per optie."""
from __future__ import annotations

import re

FEATURES = {
    "Achteruitrijcamera": r"achteruitrijcamera|parkeercamera|\bcamera\b|parking assist\w* plus",
    "360° camera": r"360\s?°?[\s-]?camera|rondomzicht|surround view|parking assist\w* plus",
    "Adaptive cruise control": r"ada?ptie?ve? cruise|cruise control adaptive|active cruise|\bacc\b|driving assist\w* (?:plus|prof)",
    "Head-up display": r"head[\s-]?up|\bhud\b",
    "Panorama-/schuifdak": r"\bpano|schuif(?!deur)|open dak|dakraam",
    "Trekhaak": r"trekhaak",
    "Leder": r"\bleder(?:en)?\b(?!\s*(?:stuur|pook))|(?<!stuurwiel )(?<!versnellingspook )\bleer\b",
    "Elektrische stoelen": r"elek\w*\.?\s*(?:voor)?stoel|stoelverstelling|stoel\(en\) elektrisch|\bmemory\b",
    "Stoelverwarming": r"stoelverwarming",
    "Stuurwielverwarming": r"stuur(?:wiel)?verwarming|stuurwiel\b[^|]*?\bverwarmd",
    "Elektrische achterklep": r"elek\w*\.?[\s-]*(?:a-klep|achterklep|klep)|achterklep elektrisch",
    "Keyless entry": r"keyless(?! start)|comfort access",
    "Harman Kardon/soundsysteem": r"harman|sound system",
    "Adaptieve/laser-koplampen": r"adaptieve? (?:led|lichten|koplamp)|koplampen adaptief|meesturende koplampen|laserlicht",
    "Dodehoekdetectie": r"dode\s?hoek|blind spot",
    "Apple CarPlay": r"car\s?play",
    "Draadloos laden": r"inductie|draadloos laden|wireless charging",
    "Standkachel": r"standkachel",
    "M Sport": r"\bm[\s/-]?sport",
}
_COMPILED = {name: re.compile(pattern, re.I) for name, pattern in FEATURES.items()}
_NEGATION = re.compile(r"\b(?:geen|zonder)\s+\S+", re.I)


# Uitvoeringslijn en audiomerk hebben op de meeste sites geen eigen plek in de optielijst. Dat ze
# daar ontbreken zegt dus niets; deze twee mogen altijd ook uit de advertentietekst komen.
_FROM_TEXT_ALWAYS = {"M Sport", "Harman Kardon/soundsysteem"}


def _detect(texts: list[str], names) -> list[str]:
    text = _NEGATION.sub(" ", " | ".join(texts))
    return [name for name in names if _COMPILED[name].search(text)]


def detect_features(options: list[str], titles: list[str]) -> tuple[list[str], str | None]:
    """Geeft (opties, herkomst). De titel is alleen het laatste redmiddel: is er een optielijst,
    dan telt die, ook als de titel meer belooft."""
    if options:
        found = set(_detect(options, FEATURES)) | set(_detect(titles, _FROM_TEXT_ALWAYS))
        return [n for n in FEATURES if n in found], "optielijst"
    found = _detect(titles, FEATURES)
    return found, "titel" if found else None
