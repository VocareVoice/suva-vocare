"""Client for the entscheidsuche.ch open-data mirror of bger.ch decisions.

bger.ch itself sits behind an Imperva/hCaptcha bot wall, so the crawl reads the
mirror: https://entscheidsuche.ch/docs/CH_BGer/ holds one `.json` (metadata)
and one `.html` (full text) file per decision, named
`CH_BGer_<signatur>_<docket>_<decision date>`.
"""

import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

BASE_URL = "https://entscheidsuche.ch/docs/CH_BGer/"
USER_AGENT = (
    "suva-vocare-fetch/0.1 (Hack Apertus Zurich research crawler; "
    "+https://github.com/VocareVoice/suva-vocare)"
)
SEARCH_URL = "https://entscheidsuche.ch/_search.php"  # Elasticsearch query endpoint
ENTRY_RE = re.compile(r'href="(CH_BGer_(\d{3})_(\d+[A-Z]+-\d+-\d{4})_(\d{4}-\d{2}-\d{2}))\.json"')
ID_RE = re.compile(r"^(CH_BGer_(\d{3})_(\d+[A-Z]+-\d+-\d{4})_(\d{4}-\d{2}-\d{2}))$")


@dataclass(frozen=True)
class Entry:
    name: str
    signatur: str
    docket: str
    decision_date: date

    @property
    def html_url(self) -> str:
        return f"{BASE_URL}{self.name}.html"


def normalise_docket(raw: str) -> str:
    """`8C-129-2025` -> `8C_129/2025`."""
    prefix, number, year = raw.split("-")
    return f"{prefix}_{number}/{year}"


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


class Client:
    def __init__(self, raw_dir: Path):
        self.cache_dir = raw_dir / "entscheidsuche"
        self.http = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(30, read=300),
            follow_redirects=True,
        )

    def close(self) -> None:
        self.http.close()

    @retry(
        retry=retry_if_exception(_retryable),
        wait=wait_exponential(multiplier=2, min=2, max=120),
        stop=stop_after_attempt(8),
        reraise=True,
    )
    def _download(self, url: str) -> bytes:
        response = self.http.get(url)
        response.raise_for_status()
        return response.content

    def get(self, url: str, cache_path: Path, refresh: bool = False) -> bytes:
        if cache_path.exists() and not refresh:
            return cache_path.read_bytes()
        body = self._download(url)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_name(cache_path.name + ".part")
        tmp.write_bytes(body)
        tmp.replace(cache_path)
        return body

    def list_entries(self, start: date, end: date, refresh: bool = False) -> list[Entry]:
        listing_path = self.cache_dir / "CH_BGer_index.html"
        if refresh or not listing_path.exists():
            print("downloading directory listing (~120 MB)...", file=sys.stderr)
        listing = self.get(BASE_URL, listing_path, refresh).decode("utf-8")
        entries = []
        for name, signatur, raw_docket, raw_date in ENTRY_RE.findall(listing):
            decision_date = date.fromisoformat(raw_date)
            if start <= decision_date <= end:
                entries.append(Entry(name, signatur, normalise_docket(raw_docket), decision_date))
        return entries

    def fetch(self, entry: Entry, suffix: str) -> bytes:
        filename = f"{entry.name}.{suffix}"
        return self.get(BASE_URL + filename, self.cache_dir / "CH_BGer" / filename)

    @retry(
        retry=retry_if_exception(_retryable),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def find(self, docket: str) -> list[Entry]:
        """The mirror's files for one docket (`8C_129/2025`), looked up through the mirror's
        search index instead of the ~120 MB directory listing. Usually one, sometimes the same
        decision under two signatures (see `pick_duplicates`)."""
        query = {
            "size": 10,
            "_source": ["id", "reference"],
            "query": {
                "bool": {
                    "filter": [{"term": {"hierarchy": "CH_BGer"}}],
                    "must": [{"match_phrase": {"reference": docket}}],
                }
            },
        }
        response = self.http.post(SEARCH_URL, json=query, timeout=30)
        response.raise_for_status()
        entries = []
        for hit in response.json().get("hits", {}).get("hits", []):
            source = hit.get("_source", {})
            match = ID_RE.match(source.get("id") or hit.get("_id", ""))
            if match is None or docket not in source.get("reference", []):
                continue
            name, signatur, raw_docket, raw_date = match.groups()
            entries.append(
                Entry(name, signatur, normalise_docket(raw_docket), date.fromisoformat(raw_date))
            )
        return entries


def pick_duplicates(client: Client, entries: list[Entry]) -> list[tuple[Entry, dict]]:
    """The mirror sometimes holds one decision under two signatures; keep the
    copy with an abstract (the bger.ch search scrape), else the newest scrape."""
    best: dict[tuple[str, date], tuple[Entry, dict]] = {}
    for entry in entries:
        meta = json.loads(client.fetch(entry, "json"))
        key = (entry.docket, entry.decision_date)
        rank = (bool(meta.get("Abstract")), meta.get("Scrapedate", ""))
        current = best.get(key)
        if current is None or rank > (
            bool(current[1].get("Abstract")),
            current[1].get("Scrapedate", ""),
        ):
            best[key] = (entry, meta)
    return list(best.values())
