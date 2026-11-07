"""Deterministic SYNTHETIC demo dataset generator.

Everything produced here is fabricated for demonstration and labeled is_synthetic=true.
It must never be presented as market observations. Run:  python -m app.seed.generate
Output: CSV snapshots + manifest.json in data/seed/ (same seed -> byte-identical files).
A few deliberately invalid rows are appended so the data-quality quarantine is exercised.
"""

import csv
import hashlib
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

from app.analytics.bond import FixedRateBond, clean_price
from app.core.config import get_settings

GENERATOR_VERSION = "1.0.0"
SEED = 20261106
START, END = date(2024, 11, 1), date(2026, 10, 30)
TENORS_M = [1, 3, 6, 12, 24, 36, 60, 84, 120, 240, 360]
CURVE_ID = "USD-UST-PAR-SYN"
SOURCE = "synthetic-generator"

SECTORS = [
    "Utilities",
    "Financials",
    "Industrials",
    "Technology",
    "Energy",
    "Healthcare",
    "Consumer",
    "Telecom",
]
RATING_SPREAD_BP = {"AAA": 35, "AA": 55, "A": 85, "BBB": 135, "BB": 250}
RATING_LADDER = list(RATING_SPREAD_BP)
NAME_A = [
    "Aldermoor",
    "Brightwater",
    "Cobalt Ridge",
    "Driftwood",
    "Emberline",
    "Fernhollow",
    "Granite Bay",
    "Harborview",
    "Ironleaf",
    "Juniper Falls",
    "Kestrel",
    "Lumen Vale",
    "Marrowgate",
    "Northcairn",
    "Oakhurst",
    "Pinecrest",
    "Quarrystone",
    "Redfern",
    "Silverbirch",
    "Tidewell",
]
NAME_B = {
    "Utilities": "Power & Light",
    "Financials": "Financial Group",
    "Industrials": "Industries",
    "Technology": "Systems",
    "Energy": "Energy Partners",
    "Healthcare": "Health",
    "Consumer": "Brands",
    "Telecom": "Communications",
}


def business_days(start: date, end: date) -> list[date]:
    days, d = [], start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def nelson_siegel(t_years: float, b0: float, b1: float, b2: float, tau: float = 2.0) -> float:
    x = t_years / tau
    f = (1 - math.exp(-x)) / x
    return b0 + b1 * f + b2 * (f - math.exp(-x))


def interp(xs: list[float], ys: list[float], x: float) -> float:
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            w = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
            return ys[i - 1] + w * (ys[i] - ys[i - 1])
    raise AssertionError("unreachable")


def round_eighth(x: float) -> float:
    return round(x * 8) / 8


def generate(out_dir: Path) -> dict:
    rng = random.Random(SEED)
    out_dir.mkdir(parents=True, exist_ok=True)
    days = business_days(START, END)

    # --- Treasury par curve: mean-reverting Nelson-Siegel factors -------------------
    b0, b1, b2 = 4.35, 0.25, -0.6
    curve_rows, curve_by_day = [], {}
    for d in days:
        b0 += 0.02 * (4.1 - b0) + rng.gauss(0, 0.045)
        b1 += 0.02 * (-0.2 - b1) + rng.gauss(0, 0.035)
        b2 += 0.02 * (-0.5 - b2) + rng.gauss(0, 0.05)
        ys = [round(nelson_siegel(m / 12, b0, b1, b2), 4) for m in TENORS_M]
        curve_by_day[d] = ys
        curve_rows += [
            {"curve_id": CURVE_ID, "as_of": d.isoformat(), "tenor_months": m, "yield_pct": y}
            for m, y in zip(TENORS_M, ys, strict=True)
        ]
    tenor_years = [m / 12 for m in TENORS_M]

    # --- Issuers, ratings ---------------------------------------------------------
    issuers, ratings, issuer_meta = [], [], {}
    issuers.append(
        {
            "id": "UST-SYN",
            "name": "U.S. Treasury (synthetic terms)",
            "sector": "Government",
            "country": "US",
        }
    )
    for i, prefix in enumerate(NAME_A):
        sector = SECTORS[i % len(SECTORS)]
        rating = rng.choices(RATING_LADDER, weights=[1, 3, 6, 7, 3])[0]
        iid = f"ISS-{i + 1:03d}"
        issuers.append(
            {
                "id": iid,
                "name": f"{prefix} {NAME_B[sector]} (synthetic)",
                "sector": sector,
                "country": "US",
            }
        )
        ratings.append(
            {
                "issuer_id": iid,
                "agency": "SYN",
                "rating": rating,
                "effective_date": START.isoformat(),
            }
        )
        meta = {
            "rating": rating,
            "spread_bp": RATING_SPREAD_BP[rating] + rng.gauss(0, 12),
            "change_day": None,
        }
        if i % 5 == 2:  # every 5th issuer gets a rating action mid-period
            idx = RATING_LADDER.index(rating)
            new = RATING_LADDER[min(max(idx + rng.choice([-1, 1]), 0), len(RATING_LADDER) - 1)]
            if new != rating:
                cd = days[rng.randrange(len(days) // 4, 3 * len(days) // 4)]
                ratings.append(
                    {
                        "issuer_id": iid,
                        "agency": "SYN",
                        "rating": new,
                        "effective_date": cd.isoformat(),
                    }
                )
                meta.update(change_day=cd, new_rating=new)
        issuer_meta[iid] = meta

    # --- Securities ---------------------------------------------------------------
    securities = []
    for n, years in enumerate([2, 3, 5, 7, 10, 20, 30, 2, 5, 10]):
        issue = START - timedelta(days=rng.randrange(30, 700))
        mat = date(issue.year + years, issue.month, min(issue.day, 28))
        securities.append(
            {
                "id": f"BM-T-{n + 1:04d}",
                "issuer_id": "UST-SYN",
                "name": f"UST {years}Y synthetic #{n + 1}",
                "bond_type": "treasury",
                "currency": "USD",
                "coupon_rate": round_eighth(interp(tenor_years, curve_by_day[days[0]], years)),
                "coupon_frequency": 2,
                "day_count": "ACT/ACT",
                "issue_date": issue.isoformat(),
                "maturity_date": mat.isoformat(),
            }
        )
    k = 0
    for iid, meta in issuer_meta.items():
        for _ in range(3):
            k += 1
            years = rng.choice([3, 4, 5, 6, 7, 8, 10, 12, 15])
            issue = START - timedelta(days=rng.randrange(30, 1500))
            mat = date(issue.year + years, issue.month, min(issue.day, 28))
            if mat <= END + timedelta(days=120):
                mat = date(END.year + rng.randint(1, 8), issue.month, min(issue.day, 28))
            cpn = interp(tenor_years, curve_by_day[days[0]], years) + meta["spread_bp"] / 100
            securities.append(
                {
                    "id": f"BM-C-{k:04d}",
                    "issuer_id": iid,
                    "name": f"{iid} {round_eighth(cpn):.3f}% {mat.year}",
                    "bond_type": "corporate",
                    "currency": "USD",
                    "coupon_rate": round_eighth(cpn),
                    "coupon_frequency": 2,
                    "day_count": "30/360",
                    "issue_date": issue.isoformat(),
                    "maturity_date": mat.isoformat(),
                }
            )
    for s in securities:
        s.update(is_callable=False, is_putable=False)

    # --- Daily quotes -------------------------------------------------------------
    quotes = []
    issuer_shock = dict.fromkeys(issuer_meta, 0.0)
    for d in days:
        for iid in issuer_shock:
            issuer_shock[iid] = 0.97 * issuer_shock[iid] + rng.gauss(0, 2.5)
        for s in securities:
            mat = date.fromisoformat(s["maturity_date"])
            if d >= mat:
                continue
            bond = FixedRateBond(
                date.fromisoformat(s["issue_date"]), mat, s["coupon_rate"] / 100, 2, s["day_count"]
            )
            t = (mat - d).days / 365.25
            y = interp(tenor_years, curve_by_day[d], t)
            if s["bond_type"] == "corporate":
                meta = issuer_meta[s["issuer_id"]]
                spread = meta["spread_bp"] + issuer_shock[s["issuer_id"]] + 4 * math.sqrt(t)
                if meta["change_day"] and d >= meta["change_day"]:
                    spread += (
                        RATING_SPREAD_BP[meta["new_rating"]] - RATING_SPREAD_BP[meta["rating"]]
                    )
                y += spread / 100 + rng.gauss(0, 0.01)
                half_ba = 0.10 + 0.02 * t
            else:
                y += rng.gauss(0, 0.003)
                half_ba = 0.01 + 0.003 * t
            mid = clean_price(bond, d, y / 100)
            quotes.append(
                {
                    "security_id": s["id"],
                    "as_of": d.isoformat(),
                    "bid_price": round(mid - half_ba, 6),
                    "ask_price": round(mid + half_ba, 6),
                    "mid_price": round(mid, 6),
                    "mid_yield_pct": round(y, 6),
                    "source": SOURCE,
                }
            )

    # --- Deliberately invalid rows (exercise quarantine; documented in README) -------
    bad_day = days[-1].isoformat()
    quotes.append(dict(quotes[-1]))  # exact duplicate
    quotes.append(
        {
            **quotes[-2],
            "security_id": "BM-C-0001",
            "as_of": bad_day,
            "mid_price": -12.5,
            "bid_price": -12.6,
            "ask_price": -12.4,
        }
    )
    quotes.append(
        {
            **quotes[-2],
            "security_id": "BM-C-0002",
            "as_of": bad_day,
            "bid_price": 101.0,
            "ask_price": 100.0,
        }
    )
    quotes.append({**quotes[-2], "security_id": "BM-X-9999"})  # unknown security
    curve_rows.append(
        {"curve_id": CURVE_ID, "as_of": bad_day, "tenor_months": 18, "yield_pct": 425.0}
    )  # bp entered as percent

    datasets = {
        "issuers": issuers,
        "securities": securities,
        "ratings": ratings,
        "curves": [
            {
                "id": CURVE_ID,
                "name": "USD Treasury par curve (synthetic)",
                "currency": "USD",
                "curve_type": "par",
                "compounding": "semiannual",
            }
        ],
        "curve_points": curve_rows,
        "quotes": quotes,
    }
    manifest = {
        "generator_version": GENERATOR_VERSION,
        "seed": SEED,
        "is_synthetic": True,
        "start": START.isoformat(),
        "end": END.isoformat(),
        "files": {},
    }
    for name, rows in datasets.items():
        path = out_dir / f"{name}.csv"
        with path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        manifest["files"][name] = {
            "rows": len(rows),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    m = generate(get_settings().seed_dir)
    print(json.dumps({k: v["rows"] for k, v in m["files"].items()}, indent=2))
