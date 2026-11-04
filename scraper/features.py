"""Herkent dure opties in optielijsten en advertentietitels, onder één naam per optie."""
from __future__ import annotations

import re

FEATURES = {
    "Achteruitrijcamera": r"achteruitrijcamera|parkeercamera|\bcamera\b|parking assist\w* plus",
    "360° camera": r"360\s?°?[\s-]?camera|rondomzicht|surround view|parking assist\w* plus",
    "Adaptive cruise control": r"ada?ptie?ve? cruise|cruise control adaptive|active cruise|\bacc\b(?!-ready)|(?<!voorbereiding )driving assist\w* (?:plus|prof)",
    "Head-up display": r"head[\s-]?up|\bhud\b",
    "Panorama-/schuifdak": r"\bpano|schuif(?!deur)|open dak|dakraam",
    "Trekhaak": r"trekhaak",
    "Leder": r"\bleder(?:en)?\b(?!\s*(?:stuur|pook))|(?<!stuurwiel )(?<!versnellingspook )\bleer\b",
    "Elektrische stoelen": r"elek\w*\.?\s*(?:voor)?stoel|stoelverstelling|stoel\(en\) elektrisch|\bmemory\b",
    "Stoelverwarming": r"stoel\s?verwarming",
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


def _detect(texts: list[str]) -> set[str]:
    text = _NEGATION.sub(" ", " | ".join(texts))
    return {name for name, pattern in _COMPILED.items() if pattern.search(text)}


def detect_features(options: list[str], titles: list[str]) -> tuple[list[str], list[str]]:
    """Geeft (alle opties, opties die alleen uit de titel komen). De optielijst is de eerste bron;
    wat daar niet in staat maar wel in de titel, telt ook mee."""
    from_list, from_title = _detect(options), _detect(titles)
    found = from_list | from_title
    return [n for n in FEATURES if n in found], [n for n in FEATURES if n in from_title - from_list]
