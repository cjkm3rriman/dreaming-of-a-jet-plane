"""Precompute app/birds.json: the birds a listener is likely to see, by region and month (DOJP-52).

Source: the GBIF occurrence API, which carries Cornell's *EOD - eBird
Observation Dataset* (CC BY 4.0, refreshed yearly). eBird's own APIs are
non-commercial only, so this is the licensed route. For every region and
calendar month we take the most-recorded species (human observations, 2015
onward) - within one region and month that tracks "likely to be seen" well
enough for a children's feature, and it surfaces seasonal migrants for free.

Regions: GADM level-1 subdivisions (states, provinces, home nations) for the
US, Canada, the UK and Australia; whole countries everywhere else. Keys are
`{ISO2}` or `{ISO2}-{subdivision name}`, matching what ipapi.co reports for
the listener (`country_code`, `region`).

The hand-written kid lines live in app/bird_lines.json, keyed by the
species' English name, so re-running this script (when GBIF's eBird snapshot
updates) only refreshes the region tables and species names.

Usage:
    uv run python scripts/build_birds.py                 # full build, ~15 min
    uv run python scripts/build_birds.py --only US,GB    # a subset of countries (ISO2)
    uv run python scripts/build_birds.py --top 10 --min-records 200
"""

import argparse
import asyncio
import json
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "app" / "birds.json"
API = "https://api.gbif.org/v1"
AVES_CLASS_KEY = 212
SUBDIVIDED = {"US": "USA", "CA": "CAN", "GB": "GBR", "AU": "AUS"}
YEAR_RANGE = "2015,2024"  # the EOD snapshot on GBIF runs to end-2024
HEADERS = {"User-Agent": "dreaming-of-a-jet-plane/birds-build (https://dreaming-of-a-jet-plane-production.up.railway.app)"}
CONCURRENCY = 4


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


async def get_json(client: httpx.AsyncClient, url: str, params: dict = None, attempts: int = 6):
    """GET with retries. Throttling (429/503/5xx) and transport blips back
    off and retry; a 4xx other than 429 is a bad request for this input
    and raises immediately so the caller can skip that region."""
    last = None
    for attempt in range(attempts):
        try:
            r = await client.get(url, params=params)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429 or r.status_code >= 500:
                last = f"HTTP {r.status_code}"
                await asyncio.sleep(min(60, 5 * 2 ** attempt))
                continue
            r.raise_for_status()
        except httpx.HTTPStatusError:
            raise
        except httpx.TransportError as e:
            last = f"{type(e).__name__}: {e}"
            await asyncio.sleep(min(60, 3 * 2 ** attempt))
    raise RuntimeError(f"gave up on {url} {params}: {last}")


async def list_regions(client: httpx.AsyncClient, only: set[str] | None) -> list[dict]:
    countries = await get_json(client, f"{API}/enumeration/country")
    regions = []
    for c in countries:
        iso2, iso3 = c["iso2"], c["iso3"]
        if only and iso2 not in only:
            continue
        if iso2 in SUBDIVIDED:
            subs = await get_json(client, f"{API}/geocode/gadm/{SUBDIVIDED[iso2]}/subdivisions", {"limit": 200})
            for sub in subs:
                name = sub["name"]
                aliases = sorted({strip_accents(name)} | {v for v in sub.get("variantName", []) if v and len(v) <= 4})
                regions.append({"key": f"{iso2}-{strip_accents(name)}", "country": iso2, "name": name,
                                "gadm": sub["id"], "aliases": aliases})
        else:
            regions.append({"key": iso2, "country": iso2, "name": c["title"], "gadm": iso3, "aliases": []})
    return regions


async def top_species(client: httpx.AsyncClient, gadm: str, month: int, top: int) -> tuple[int, list[tuple[int, int]]]:
    data = await get_json(client, f"{API}/occurrence/search", {
        "classKey": AVES_CLASS_KEY, "basisOfRecord": "HUMAN_OBSERVATION", "gadmGid": gadm,
        "month": month, "year": YEAR_RANGE, "limit": 0, "facet": "speciesKey", "facetLimit": top + 4,
    })
    facets = data.get("facets") or []
    counts = facets[0]["counts"] if facets else []
    return data.get("count", 0), [(int(f["name"]), int(f["count"])) for f in counts]


async def species_names(client: httpx.AsyncClient, key: int) -> dict:
    sp = await get_json(client, f"{API}/species/{key}")
    return {"name": sp.get("vernacularName"), "scientific": sp.get("canonicalName")}


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="comma-separated ISO2 country codes to (re)build")
    ap.add_argument("--top", type=int, default=10, help="species kept per region-month")
    ap.add_argument("--min-records", type=int, default=200, help="skip a region-month with fewer records")
    ap.add_argument("--resume", action="store_true", help="keep regions already in app/birds.json and build only the rest")
    args = ap.parse_args()
    only = {c.strip().upper() for c in args.only.split(",")} if args.only else None

    existing = json.loads(OUT.read_text()) if OUT.exists() else {}
    species = existing.get("species", {})
    region_tables = existing.get("regions", {}) if (only or args.resume) else {}
    failed: list[str] = []

    started = time.time()
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(timeout=60.0, headers=HEADERS) as client:
        regions = await list_regions(client, only)
        if args.resume:
            regions = [r for r in regions if r["key"] not in region_tables]
        print(f"{len(regions)} regions x 12 months", flush=True)
        done = 0

        def checkpoint():
            OUT.write_text(json.dumps({"_partial": True, "regions": region_tables, "species": species},
                                      ensure_ascii=False))

        async def build(region: dict):
            nonlocal done
            months = {}
            async def one_month(month: int):
                async with sem:
                    return month, await top_species(client, region["gadm"], month, args.top)
            try:
                for month, (total, ranked) in await asyncio.gather(*(one_month(m) for m in range(1, 13))):
                    if total >= args.min_records:
                        months[str(month)] = [k for k, _ in ranked[:args.top + 4]]
            except Exception as e:  # one bad region must not sink the build
                print(f"  SKIP {region['key']} ({region['gadm']}): {e}", flush=True)
                failed.append(region["key"])
                months = {}
            if months:
                region_tables[region["key"]] = {
                    "country": region["country"], "name": region["name"], "gadm": region["gadm"],
                    "aliases": region["aliases"], "months": months,
                }
            done += 1
            if done % 10 == 0 or done == len(regions):
                print(f"  {done}/{len(regions)} regions, {time.time() - started:.0f}s", flush=True)
                checkpoint()

        # Regions run one at a time (a region's 12 months run concurrently
        # under the semaphore), so a checkpoint always holds whole regions
        for region in regions:
            await build(region)

        wanted = {k for t in region_tables.values() for ks in t["months"].values() for k in ks}
        missing = [k for k in wanted if str(k) not in species or not species[str(k)].get("name")]
        print(f"{len(wanted)} species referenced, resolving {len(missing)} names", flush=True)

        async def resolve(key: int):
            async with sem:
                try:
                    species[str(key)] = await species_names(client, key)
                except Exception as e:
                    print(f"  SKIP species {key}: {e}", flush=True)
        await asyncio.gather(*(resolve(k) for k in missing))

    # Drop species with no English vernacular name: nothing to narrate. Trim
    # each month list to `top` narratable species.
    narratable = {k for k, v in species.items() if v.get("name")}
    for table in region_tables.values():
        for m, keys in table["months"].items():
            table["months"][m] = [k for k in keys if str(k) in narratable][:args.top]

    OUT.write_text(json.dumps({
        "_attribution": "Bird data from the EOD - eBird Observation Dataset (Cornell Lab of Ornithology), "
                        "accessed via GBIF (https://www.gbif.org/dataset/4fa7b334-ce0d-4e88-aaae-2e0c138d049e), "
                        "CC BY 4.0. Species lists are the most-recorded species per region and calendar month, "
                        "human observations 2015 onward. Kid-facing lines are hand-written in bird_lines.json.",
        "generated": date.today().isoformat(),
        "top": args.top,
        "regions": dict(sorted(region_tables.items())),
        "species": dict(sorted(species.items(), key=lambda kv: int(kv[0]))),
    }, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}: {len(region_tables)} regions, {len(species)} species, {time.time() - started:.0f}s"
          + (f"; FAILED regions: {failed}" if failed else ""))


if __name__ == "__main__":
    asyncio.run(main())
