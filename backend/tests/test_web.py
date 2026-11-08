"""Single-container production mode: static frontend, SPA fallback, headers, rate limit."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web import install_frontend, install_rate_limit, install_security_headers


def make_app(tmp_path, per_minute=0):
    (tmp_path / "index.html").write_text("<html>bondMIND</html>")
    (tmp_path / "main-ABC123.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("nope")
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    install_security_headers(app)
    if per_minute:
        install_rate_limit(app, per_minute)
    install_frontend(app, tmp_path)
    return TestClient(app)


def test_serves_assets_and_spa_fallback(tmp_path):
    c = make_app(tmp_path)
    r = c.get("/main-ABC123.js")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    deep = c.get("/bonds/BM-C-0001")  # client-side route
    assert deep.status_code == 200 and "bondMIND" in deep.text
    assert deep.headers["x-content-type-options"] == "nosniff"
    assert c.get("/api/nope").status_code == 404
    assert c.get("/api/ping").json() == {"ok": True}


def test_no_path_traversal(tmp_path):
    c = make_app(tmp_path)
    r = c.get("/../secret.txt")
    assert "nope" not in r.text


def test_rate_limit(tmp_path):
    c = make_app(tmp_path, per_minute=3)
    codes = [c.get("/api/ping").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    assert c.get("/bonds").status_code == 200  # pages are not rate limited
