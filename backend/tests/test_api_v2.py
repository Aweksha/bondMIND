"""v2 API: Requirements 2.0 acceptance examples (sec. 10) and failure modes."""

from datetime import date

from app.models import Security

BASE = "2026-11-06"


def evaluate(client, **overrides):
    body = {
        "curveId": "USD-UST-PAR",
        "baseDate": BASE,
        "securityIds": ["BM-C-0001"],
        "shockNodes": [{"tenorYears": 1, "bp": 50}],
        "spreadMode": "hold_constant",
    }
    body.update(overrides)
    return client.post("/api/v2/scenarios/evaluate", json=body)


def test_example_a_parallel_shock_reprices_bond(client):
    r = evaluate(client)
    assert r.status_code == 200, r.text
    body = r.json()
    res = body["results"][0]
    assert res["status"] == "ok"
    assert res["shocked"]["clean"] < res["base"]["clean"]
    assert res["change"]["pct"] < 0
    assert res["base"]["dv01"] < 0 and res["base"]["effective_duration"] > 0
    # every shocked par point moved exactly +50bp
    assert all(abs(p["shock_bp"] - 50) < 1e-6 for p in body["curve"]["points"])
    # duration/convexity approximation within a few cents for +50bp
    assert abs(res["approximation"]["error_vs_full"]) < 0.05
    for key in (
        "input",
        "units",
        "warnings",
        "vintage",
        "engine_version",
        "calculated_at",
        "methodology",
        "request_id",
    ):
        assert key in body
    assert res["assumptions"]["settlement_convention"].startswith("T+0")
    assert body["vintage"]["source"].startswith("U.S. Department of the Treasury")


def test_example_b_overlay_two_dates_with_gaps(client):
    r = client.get(
        "/api/v2/curves/USD-UST-PAR/observations",
        params=[
            ("dates", "2026-11-06"),
            ("dates", "2024-11-06"),
            ("tenors", 1.5),
            ("tenors", 24),
            ("tenors", 60),
            ("tenors", 120),
            ("tenors", 360),
        ],
    )
    assert r.status_code == 200, r.text
    obs = r.json()["observations"]
    assert [o["status"] for o in obs] == ["observed", "observed"]
    now = {p["tenor_months"]: p["yield_pct"] for p in obs[0]["points"]}
    then = {p["tenor_months"]: p["yield_pct"] for p in obs[1]["points"]}
    assert all(v is not None for v in now.values())
    # the 1.5M bill did not exist in Nov 2024: shown as a gap, never 0 or interpolated
    assert then[1.5] is None and then[120] is not None


def test_weekend_resolves_to_prior_observation_and_says_so(client):
    obs = client.get(
        "/api/v2/curves/USD-UST-PAR/observations", params={"dates": "2026-11-01"}
    ).json()["observations"][0]  # a Sunday
    assert obs["status"] == "prior_observation" and obs["observed_date"] == "2026-10-30"
    far = client.get(
        "/api/v2/curves/USD-UST-PAR/observations", params={"dates": "2010-01-04"}
    ).json()["observations"][0]
    assert far["status"] == "unavailable" and far["points"] == []


def test_example_c_twist_with_spread_shock_is_reproducible(client):
    kwargs = {
        "shockNodes": [{"tenorYears": 2, "bp": -25}, {"tenorYears": 10, "bp": 50}],
        "spreadMode": "shock",
        "spreadShockBp": 20,
        "securityIds": ["BM-C-0001", "BM-T-0003"],
    }
    a, b = evaluate(client, **kwargs).json(), evaluate(client, **kwargs).json()
    assert a["results"] == b["results"]
    assert a["curve"]["is_parallel"] is False
    shocks = {p["tenor_months"]: p["shock_bp"] for p in a["curve"]["points"]}
    assert shocks[12] == -25 and shocks[360] == 50 and abs(shocks[60] - 3.125) < 1e-9
    assert a["results"][0]["shocked_z_spread_bp"] - a["results"][0]["z_spread_bp"] == 20


def test_security_analytics(client):
    r = client.get("/api/v2/securities/BM-C-0001/analytics")
    assert r.status_code == 200, r.text
    a = r.json()
    p = a["pricing"]
    assert abs(p["dirty"] - p["clean"] - p["accrued"]) < 1e-9
    # curve model with calibrated Z-spread reproduces the market dirty price
    assert abs(a["curve_risk"]["model_dirty"] - p["dirty"]) < 1e-6
    assert abs(sum(cf["present_value"] for cf in a["cash_flows"]) - p["dirty"]) < 1e-6
    assert a["yield_risk"]["dv01"] < 0
    assert a["assumptions"]["day_count"].startswith("30/360")


def test_validation_errors(client):
    assert evaluate(client, shockNodes=[{"tenorYears": 1, "bp": 400}]).status_code == 422
    assert evaluate(client, shockNodes=[{"tenorYears": 40, "bp": 10}]).status_code == 422
    assert evaluate(client, spreadShockBp=10).status_code == 422  # needs spreadMode=shock
    r = evaluate(client, curveId="EUR-NOPE")
    assert r.status_code == 404 and r.json()["code"] == "unknown_curve"
    assert evaluate(client, baseDate="2010-01-04").json()["code"] == "no_curve_observation"


def test_partial_failure_does_not_fail_other_securities(client, session_factory):
    with session_factory() as s:
        if s.get(Security, "BM-CALL-1") is None:
            s.add(
                Security(
                    id="BM-CALL-1",
                    issuer_id="ISS-001",
                    name="callable test",
                    bond_type="corporate",
                    currency="USD",
                    coupon_rate=5,
                    coupon_frequency=2,
                    day_count="30/360",
                    issue_date=date(2024, 1, 1),
                    maturity_date=date(2030, 1, 1),
                    is_callable=True,
                    source="test",
                    is_synthetic=True,
                )
            )
            s.commit()
    body = evaluate(client, securityIds=["BM-C-0001", "BM-CALL-1", "NOPE"]).json()
    status = {r["security_id"]: r["status"] for r in body["results"]}
    assert status == {"BM-C-0001": "ok", "BM-CALL-1": "error", "NOPE": "error"}
    errors = {r["security_id"]: r["error"]["code"] for r in body["results"] if "error" in r}
    assert errors == {"BM-CALL-1": "unsupported_instrument", "NOPE": "not_found"}
    r = client.get("/api/v2/securities/BM-CALL-1/analytics")
    assert r.status_code == 422 and r.json()["code"] == "unsupported_instrument"
