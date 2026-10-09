"""Download IBKR's TWS API guide as Markdown into docs/ibkr-tws-api/ (not committed).

IBKR publishes every page as clean Markdown (page URL + ".md") and lists them in
llms.txt. The pages are IBKR's copyright, so they are fetched on demand for
local reference and kept out of git; docs/ibkr-tws-api-notes.md holds the facts
Sapient relies on, in our own words, with links back to the pages.

    uv run python scripts/fetch_ibkr_docs.py          # stdlib only, ~2 MB, ~340 pages
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import time
import urllib.request

BASE = "https://www.interactivebrokers.com/docs/tws-api/"
OUT = Path(__file__).resolve().parent.parent / "docs" / "ibkr-tws-api"


def get(url: str, tries: int = 3) -> str:
    for attempt in range(tries):
        try:
            # IBKR's CDN refuses Python's default User-Agent (HTTP 403).
            request = urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0", "Accept": "text/markdown, */*"})
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8")
        except OSError:
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def main() -> None:
    index = get(BASE + "llms.txt")
    # Links point at ibkrcampus.com; the same paths are served from BASE.
    paths = sorted(set(re.findall(r"\]\(https://[^/]+/docs/tws-api/((?:doc|changelog)[^)]*\.md)\)", index)))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.md").write_text(index, encoding="utf-8")

    def fetch(path: str) -> str | None:
        try:
            (OUT / path.replace("/", "_")).write_text(get(BASE + path), encoding="utf-8")
            return None
        except OSError as exc:
            return f"{path}: {exc}"

    with ThreadPoolExecutor(max_workers=6) as pool:
        failures = [f for f in pool.map(fetch, paths) if f]
    print(f"{len(paths) - len(failures)} of {len(paths)} pages saved to {OUT}")
    for failure in failures:
        print("failed:", failure)


if __name__ == "__main__":
    main()
