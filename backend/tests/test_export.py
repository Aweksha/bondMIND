"""The static site must show exactly what the API computes."""

import json

import pytest

from app.export.static_site import export


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    export(out)
    return out


def load(site, rel):
    return json.loads((site / rel).read_text())


def test_bond_list_matches_api(site, client):
    exported = {b["id"]: b for b in load(site, "bonds.json")["items"]}
    api = {
        b["id"]: b for b in client.get("/api/v2/bonds", params={"page_size": 200}).json()["items"]
    }
    # other tests add throwaway bonds to the shared test DB; compare the seeded universe
    assert len(exported) == 70 and set(exported) <= set(api)
    for bid, b in exported.items():
        for k in ("mid_yield_pct", "modified_duration", "g_spread_bp", "years"):
            assert api[bid][k] == pytest.approx(b[k], abs=1e-6), (bid, k)


def test_bond_detail_and_simulator_match_api(site, client):
    d = load(site, "bonds/BM-C-0001.json")
    a = client.get("/api/v2/securities/BM-C-0001/analytics").json()
    assert d["analytics"]["pricing"]["dirty"] == pytest.approx(a["pricing"]["dirty"], abs=1e-6)
    assert d["analytics"]["curve_risk"]["dv01"] == pytest.approx(a["curve_risk"]["dv01"], abs=1e-6)
    assert len(d["history"]["points"]) > 400
    py = load(site, "price-yield/BM-T-0007.json")
    api_py = client.get(
        "/api/v2/securities/BM-T-0007/price-yield", params={"range_bp": 300, "step_bp": 1}
    ).json()
    assert len(py["points"]) == len(api_py["points"]) == 601
    assert py["points"][450]["clean"] == pytest.approx(api_py["points"][450]["clean"], abs=1e-6)


def test_curve_history_keeps_gaps(site):
    c = load(site, "curve.json")
    assert c["dates"][0] == "2019-01-02" and c["is_synthetic"] is False
    i = c["dates"].index("2024-11-06")
    assert c["yields"]["1.5"][i] is None and c["yields"]["120"][i] is not None
    assert all(len(v) == len(c["dates"]) for v in c["yields"].values())


def test_no_secrets_or_local_paths_in_export(site):
    for path in site.rglob("*.json"):
        text = path.read_text()
        assert "/Users/" not in text and "password" not in text.lower(), path
