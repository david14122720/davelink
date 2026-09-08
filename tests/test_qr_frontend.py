"""Slice 5: QR frontend/UX hooks.

Asserts the served ``index.html`` exposes every Slice 5 control hook and the
served ``app.js`` implements per-panel state over the Slice 4 backend
contract (binary GET + POST /api/qr/raw, no silent DB writes).
"""


def test_index_has_qr_customization_hooks(client):
    """Both QR panels expose the full Slice 5 control set."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.text

    # Per-panel roots + warning badges
    assert 'data-qr-panel="section"' in html
    assert 'data-qr-panel="result"' in html
    assert html.count("data-qr-warning") >= 2

    # Controls: back color, size, EC, logo presets, format toggle, border
    for hook in (
        'name="back_color"',
        'name="size"',
        'name="error_correction"',
        'name="logo"',
        'name="format"',
        'name="border"',
        'name="dot_style"',
        'name="fill_color"',
    ):
        assert hook in html, f"missing control hook {hook}"

    # All four logo presets offered, PNG-only controls flagged for SVG mode
    for preset in ('value="davelink"', 'value="link"', 'value="star"', 'value="heart"'):
        assert preset in html, f"missing logo preset {preset}"
    assert "data-png-only" in html

    # PNG + SVG download buttons on both panels
    for button_id in (
        "download-qr-png",
        "download-qr-svg",
        "download-qr-result-png",
        "download-qr-result-svg",
    ):
        assert f'id="{button_id}"' in html, f"missing button {button_id}"


def test_app_js_per_panel_state_and_raw_endpoint(client):
    """app.js uses a per-panel factory + raw endpoint, no shared singleton."""
    response = client.get("/js/app.js")
    assert response.status_code == 200
    js = response.text

    # Per-panel state factory; each panel renders from its own config
    assert "makeQrPanel" in js
    assert "sectionPanel" in js and "resultPanel" in js
    # Shared qrConfig singleton is gone (per-panel regression guard)
    assert "const qrConfig" not in js

    # Slice 4 contract: binary GET + no-DB raw POST; debounced live preview
    assert "/api/qr/raw" in js
    assert ".png" in js and ".svg" in js
    assert "300" in js  # 300ms debounce kept

    # Standalone panel must not create Link rows: /api/shorten appears exactly
    # once — the main shorten form — and never on the QR generator path.
    assert js.count("api/shorten") == 1

    # Inline warnings/errors, never alert()
    assert "data-qr-warning" in js or "qr-warning" in js
    assert "alert(" not in js
