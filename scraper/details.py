"""Haalt opties van losse advertentiepagina's, met een cache per advertentie.

Opties van een geplaatste advertentie veranderen vrijwel niet. Dankzij de cache gaat een afgebroken
run verder waar hij was en belast een nieuwe run de site alleen voor nieuwe advertenties.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
SAVE_EVERY = 25
# Levert dit aantal pagina's op rij niets op, dan is de site vrijwel zeker veranderd.
EMPTY_LIMIT = 30


def enrich(fetcher, run, parse: Callable[[str], list[str]], cache_dir: Path | None = None) -> None:
    directory = cache_dir or CACHE_DIR
    path = directory / f"{run.site}.json"
    cache: dict[str, list[str]] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def save() -> None:
        directory.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    def apply() -> None:
        for listing in run.listings.values():
            listing["options"] = cache.get(listing["source_id"], listing.get("options") or [])

    todo = [l for l in run.listings.values() if l["source_id"] not in cache]
    print(f"  [{run.site}] opties: {len(cache)} in cache, {len(todo)} op te halen", flush=True)
    empties, missing = [], 0
    try:
        for done, listing in enumerate(todo, 1):
            page = fetcher.get(listing["url"])
            if page is None:
                missing += 1  # advertentie net verwijderd of niet toegestaan: niet cachen
                continue
            options = parse(page.text)
            cache[listing["source_id"]] = options
            empties = [*empties, listing["source_id"]] if not options else []
            if len(empties) >= EMPTY_LIMIT:
                for source_id in empties:
                    del cache[source_id]
                run.status = "fout"
                run.note(f"Opties gestopt: {EMPTY_LIMIT} pagina's op rij zonder opties, de parser is waarschijnlijk verouderd")
                return
            if done % SAVE_EVERY == 0:
                save()
                print(f"  [{run.site}] opties {done}/{len(todo)}", flush=True)
    finally:
        # Ook bij een blokkade of onderbreking blijft bewaard wat al binnen is.
        save()
        apply()
        without = sum(not l["options"] for l in run.listings.values())
        run.options_missing = without
        if missing:
            run.note(f"{missing} advertentiepagina's niet beschikbaar")
