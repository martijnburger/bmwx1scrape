"""Gebruik: python3 -m scraper [--sites a,b] [--delay 3] [--merge-only]"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .fetch import BlockedError, Fetcher, RequestLimitReached
from .merge import merge_listings
from .sources import DEFAULT_SITES, SOURCES

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"


class Run:
    def __init__(self, site: str):
        self.site = site
        self.expected: int | None = None
        self.listings: dict[str, dict] = {}
        self.notes: list[str] = []
        self.status = "ok"
        self.skipped = 0  # bewust overgeslagen, bijvoorbeeld nieuwe auto's
        self.options_missing: int | None = None

    @property
    def count(self) -> int:
        return len(self.listings)

    def add_all(self, items: list[dict]) -> None:
        new = sum(1 for i in items if i["source_id"] not in self.listings)
        for item in items:
            self.listings[item["source_id"]] = item
        total = f"/{self.expected}" if self.expected else ""
        print(f"  [{self.site}] +{new} nieuw, totaal {self.count}{total}", flush=True)

    def note(self, text: str) -> None:
        self.notes.append(text)
        print(f"  [{self.site}] {text}", flush=True)

    def missed(self, count: int, reason: str) -> None:
        self.note(f"{reason} (circa {count} niet zichtbaar)")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def scrape_site(site: str, delay: float, max_requests: int) -> None:
    print(f"\n== {site} ==", flush=True)
    fetcher = Fetcher(delay=delay, max_requests=max_requests)
    run = Run(site)
    started = time.monotonic()
    try:
        SOURCES[site].crawl(fetcher, run)
    except BlockedError as error:
        run.status = "geblokkeerd"
        run.note(f"Gestopt, site weigert toegang: {error}")
    except RequestLimitReached as error:
        run.status = "onvolledig"
        run.note(str(error))
    except KeyboardInterrupt:
        run.status = "onderbroken"
        run.note("Onderbroken door gebruiker")
        save_run(run, fetcher, started)
        raise
    except Exception as error:  # een kapotte parser mag de overige sites niet tegenhouden
        run.status = "fout"
        run.note(f"Onverwachte fout: {type(error).__name__}: {error}")
    if fetcher.skipped_by_robots:
        run.note(f"{len(fetcher.skipped_by_robots)} URL's overgeslagen vanwege robots.txt")
    if run.status == "ok" and run.expected and run.count + run.skipped < run.expected:
        run.status = "onvolledig"
    save_run(run, fetcher, started)


def save_run(run: Run, fetcher: Fetcher, started: float) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f"{run.site}.json"
    # Een afgebroken run mag een eerdere, grotere oogst niet overschrijven.
    if run.status != "ok" and path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if len(previous.get("listings", [])) > run.count:
            print(f"  [{run.site}] eerdere oogst ({len(previous['listings'])}) blijft bewaard", flush=True)
            return
    path.write_text(json.dumps({
        "site": run.site, "status": run.status, "expected": run.expected, "collected": run.count,
        "skipped": run.skipped, "options_missing": run.options_missing,
        "requests": fetcher.requests, "seconds": round(time.monotonic() - started),
        "notes": run.notes, "scraped_at": now(), "listings": list(run.listings.values()),
    }, ensure_ascii=False), encoding="utf-8")
    print(f"  [{run.site}] klaar: {run.status}, {run.count} advertenties, {fetcher.requests} verzoeken", flush=True)


def merge_all() -> None:
    listings, report = [], []
    for path in sorted(RAW.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        listings += data.pop("listings", [])
        report.append(data)
    cars = merge_listings(listings)
    (DATA / "listings.json").write_text(json.dumps(cars, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "report.json").write_text(json.dumps({
        "generated_at": now(), "cars": len(cars), "ads": len(listings), "sites": report,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(listings)} advertenties → {len(cars)} unieke auto's in {DATA / 'listings.json'}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="python3 -m scraper", description=__doc__)
    parser.add_argument("--sites", default=",".join(DEFAULT_SITES),
                        help=f"kommagescheiden, keuze uit: {', '.join(SOURCES)}")
    parser.add_argument("--delay", type=float, default=3.0, help="seconden tussen verzoeken per site (min. 1)")
    parser.add_argument("--max-requests", type=int, default=3000, help="maximum aantal verzoeken per site")
    parser.add_argument("--merge-only", action="store_true", help="alleen data/raw opnieuw samenvoegen")
    args = parser.parse_args()

    if not args.merge_only:
        sites = [s.strip() for s in args.sites.split(",") if s.strip()]
        unknown = [s for s in sites if s not in SOURCES]
        if unknown:
            parser.error(f"onbekende site(s): {', '.join(unknown)}")
        for site in sites:
            scrape_site(site, max(args.delay, 1.0), args.max_requests)
    merge_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
