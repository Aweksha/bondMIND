"""Connector: U.S. Department of the Treasury daily par yield curve rates (public domain).

Run:  python -m app.ingest.ust_treasury --from-year 2019 --to-year 2026
Writes data/seed/ust_par_curve.csv (normalised long format) and ust_par_curve.meta.json
(source URL, retrieval time, row counts). The snapshot is committed so the app and tests run
offline and reproducibly; re-running the connector refreshes it.

Missing cells (tenors not published on a date) are omitted, never filled.
"""

import argparse
import csv
import hashlib
import io
import json
import urllib.request
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from app.core.config import get_settings

CURVE_ID = "USD-UST-PAR"
SOURCE = "us-treasury"
URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
    "&field_tdr_date_value={year}&page&_format=csv"
)
# Column header -> tenor in months
TENORS = {
    "1 Mo": "1",
    "1.5 Month": "1.5",
    "2 Mo": "2",
    "3 Mo": "3",
    "4 Mo": "4",
    "6 Mo": "6",
    "1 Yr": "12",
    "2 Yr": "24",
    "3 Yr": "36",
    "5 Yr": "60",
    "7 Yr": "84",
    "10 Yr": "120",
    "20 Yr": "240",
    "30 Yr": "360",
}
MAX_BYTES = 2_000_000


def fetch_year(year: int) -> str:
    url = URL.format(year=year)  # fixed https host; year is an int
    req = urllib.request.Request(url, headers={"User-Agent": "bondMIND-research-client"})  # noqa: S310
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        if "csv" not in resp.headers.get("Content-Type", ""):
            raise RuntimeError(f"{year}: unexpected content type {resp.headers['Content-Type']}")
        body = resp.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise RuntimeError(f"{year}: response larger than {MAX_BYTES} bytes")
    return body.decode("utf-8")


def normalise(text: str) -> list[dict]:
    rows = []
    for raw in csv.DictReader(io.StringIO(text)):
        as_of = datetime.strptime(raw["Date"], "%m/%d/%Y").date()  # noqa: DTZ007
        for header, months in TENORS.items():
            cell = (raw.get(header) or "").strip()
            if not cell or cell.upper() == "N/A":
                continue
            try:
                value = Decimal(cell)
            except InvalidOperation as exc:
                raise ValueError(f"{as_of} {header}: non-numeric {cell!r}") from exc
            rows.append(
                {
                    "curve_id": CURVE_ID,
                    "as_of": as_of.isoformat(),
                    "tenor_months": months,
                    "yield_pct": str(value),
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-year", type=int, default=2019)
    parser.add_argument("--to-year", type=int, default=date.today().year)
    args = parser.parse_args()
    rows: list[dict] = []
    for year in range(args.from_year, args.to_year + 1):
        year_rows = normalise(fetch_year(year))
        print(f"{year}: {len(year_rows)} observations")
        rows += year_rows
    rows.sort(key=lambda r: (r["as_of"], Decimal(r["tenor_months"])))
    out = get_settings().seed_dir
    path = out / "ust_par_curve.csv"
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    dates = sorted({r["as_of"] for r in rows})
    meta = {
        "source": "U.S. Department of the Treasury, Daily Treasury Par Yield Curve Rates",
        "source_url": URL.format(year="{year}"),
        "license": "U.S. Government work, public domain",
        "units": "percent, bond-equivalent (semiannual) par yields",
        "retrieved_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "first_date": dates[0],
        "last_date": dates[-1],
        "dates": len(dates),
        "rows": len(rows),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "staleness_hint_days": (date.today() - date.fromisoformat(dates[-1])).days
        if dates
        else None,
    }
    (out / "ust_par_curve.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({k: meta[k] for k in ("first_date", "last_date", "dates", "rows")}))


if __name__ == "__main__":
    main()
