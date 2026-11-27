"""The UVG (SR 832.20) by its old names. Everything lives in `suva.laws`, which also holds the
ATSG and the UVV; this module keeps the UVG-only names that existing callers use."""

from typing import Any

from suva import laws
from suva.laws import LANGS, key, parse  # noqa: F401  (re-exported)

UVG = laws.LAWS["UVG"]
ELI = f"https://fedlex.data.admin.ch/eli/{UVG.eli}"
PAGE_URL = UVG.base_url + "{lang}#{anchor}"
SNAPSHOT = UVG.snapshot
LAW_NAMES = UVG.names


def fetch() -> dict[str, Any]:
    return laws.fetch("UVG")


def articles(lang: str = "de") -> dict[str, dict[str, Any]]:
    return laws.articles(lang, "UVG")


def in_force(lang: str = "de") -> str:
    return laws.in_force(lang, "UVG")


def get(number: str, lang: str = "de") -> dict[str, Any] | None:
    return laws.get(number, lang, "UVG")


def outline(lang: str = "de") -> str:
    return laws.outline(lang, "UVG")
