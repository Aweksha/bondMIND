def test_health(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_securities_paginated_and_labelled_synthetic(client):
    body = client.get("/api/v1/securities", params={"page_size": 10}).json()
    assert body["total"] == 70
    assert len(body["items"]) == 10
    assert body["context"]["is_synthetic"] is True


def test_securities_filters_and_sort(client):
    body = client.get(
        "/api/v1/securities",
        params={"bond_type": "corporate", "rating": ["BBB"], "sort": "-mid_yield_pct"},
    ).json()
    ys = [i["mid_yield_pct"] for i in body["items"]]
    assert body["items"] and all(i["rating"] == "BBB" for i in body["items"])
    assert ys == sorted(ys, reverse=True)


def test_invalid_sort_uses_error_contract(client):
    r = client.get("/api/v1/securities", params={"sort": "bogus"})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "invalid_sort" and body["request_id"]


def test_security_detail_and_404(client):
    d = client.get("/api/v1/securities/BM-C-0001").json()
    assert d["bid_price"] < d["mid_price"] < d["ask_price"]
    assert d["day_count"] == "30/360"
    r = client.get("/api/v1/securities/NOPE")
    assert r.status_code == 404 and r.json()["code"] == "not_found"


def test_curves(client):
    curves = client.get("/api/v1/curves").json()
    assert curves[0]["id"] == "USD-UST-PAR" and curves[0]["is_synthetic"] is False
    snap = client.get(f"/api/v1/curves/{curves[0]['id']}/points").json()
    assert snap["context"]["is_synthetic"] is False
    assert [p["tenor_months"] for p in snap["points"]][:3] == [1, 1.5, 2]
    assert snap["points"][-1]["tenor_months"] == 360


def test_overview_and_quality(client):
    ov = client.get("/api/v1/market/overview").json()
    assert ov["curve"] and ov["avg_spread_by_rating_bp"]
    assert {f["status"] for f in ov["freshness"]} == {"fresh"}
    dq = client.get("/api/v1/data-quality").json()
    assert sum(dq["issues_by_rule"].values()) == 5
