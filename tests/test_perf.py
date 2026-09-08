"""
Slice 2: GZip compression — JSON/SVG yes, PNG no (redirect-performance spec).
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from fastapi.testclient import TestClient

from backend.fastapi_app.main import NoPngGzipMiddleware, app


def test_main_app_registers_gzip_middleware():
    """NoPngGzipMiddleware must wrap the app (JSON/SVG compressed)."""
    assert any(
        getattr(entry, "cls", None) is NoPngGzipMiddleware
        for entry in app.user_middleware
    )


def test_json_responses_are_gzipped(client, db_session, fake_redis):
    """A stats payload over minimum_size carries Content-Encoding: gzip."""
    from backend.shared.models import Analytics, Link

    code = "gzipstats"
    link = Link(codigo=code, url_original="https://example.com/gzip-stats")
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)

    # Pad the payload well past the 500-byte GZip minimum.
    for i in range(12):
        db_session.add(
            Analytics(
                link_id=link.id,
                ip_address=f"10.9.8.{i}",
                user_agent="gzip-probe-agent/1.0 " + ("x" * 120),
                referer="https://referer.example/long-path",
            )
        )
    db_session.commit()

    response = client.get(f"/api/stats/{code}", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert len(response.content) > 500
    assert response.headers.get("content-encoding") == "gzip"


def test_png_paths_skip_gzip_but_json_does_not():
    """`.png` binary routes bypass compression; JSON of equal size compresses."""
    tiny = FastAPI()
    tiny.add_middleware(NoPngGzipMiddleware, minimum_size=500)

    big_png = b"\x89PNG" + (b"\x00" * 2000)

    @tiny.get("/img.png")
    def serve_png():
        return Response(content=big_png, media_type="image/png")

    @tiny.get("/data.json")
    def serve_json():
        return JSONResponse(content={"blob": "y" * 2000})

    with TestClient(tiny) as tiny_client:
        png = tiny_client.get("/img.png", headers={"Accept-Encoding": "gzip"})
        assert png.status_code == 200
        assert png.headers.get("content-encoding") is None
        assert png.content == big_png

        js = tiny_client.get("/data.json", headers={"Accept-Encoding": "gzip"})
        assert js.status_code == 200
        assert js.headers.get("content-encoding") == "gzip"
