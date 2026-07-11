"""
Tests for rate limiting behavior.

The app uses slowapi with a 10/second limit on /api/* endpoints.
The redirect endpoint (GET /{code}) is NOT rate-limited.

Note: Since other tests may have consumed some of the rate limit budget,
these tests send requests until a 429 is received rather than expecting
an exact count.
"""

import pytest


def test_shorten_rate_limit_eventually_returns_429(client):
    """Verify that sending enough rapid requests to shorten eventually triggers 429"""
    url_template = "https://example.com/ratelimit-{}"

    last_status = None
    codes_created = 0

    for i in range(25):
        response = client.post(
            "/api/shorten",
            json={"url": url_template.format(i)},
        )
        last_status = response.status_code
        if response.status_code == 200:
            codes_created += 1
        elif response.status_code == 429:
            break

    assert last_status == 429, (
        f"Rate limit was never triggered after 25 requests. "
        f"Created {codes_created} codes, last status: {last_status}"
    )


def test_rate_limit_response_has_retry_after_and_detail(client):
    """Verify 429 response includes Retry-After header and detail field"""
    url_template = "https://example.com/retryafter-{}"

    response_429 = None
    for i in range(25):
        resp = client.post(
            "/api/shorten",
            json={"url": url_template.format(i)},
        )
        if resp.status_code == 429:
            response_429 = resp
            break

    assert response_429 is not None, "Rate limit was never triggered"
    assert response_429.status_code == 429

    data = response_429.json()
    assert "detail" in data, "429 response should have detail field"

    # Check Retry-After header
    retry_after = response_429.headers.get("retry-after")
    assert retry_after is not None, "429 response should have Retry-After header"
    retry_value = float(retry_after)
    assert retry_value >= 0, f"Retry-After should be >= 0, got {retry_value}"


def test_redirect_not_rate_limited(client, db_session):
    """Verify redirect endpoint bypasses rate limiting (no decorator)"""
    from backend.shared.models import Link

    code = "nolimit"
    link = Link(codigo=code, url_original="https://example.com/no-rate-limit")
    db_session.add(link)
    db_session.commit()

    # Send 20 rapid redirect requests — none should be 429
    for _ in range(20):
        response = client.get(f"/{code}", follow_redirects=False)
        assert response.status_code == 302, (
            f"Redirect should not be rate limited, got {response.status_code}"
        )


def test_stats_rate_limited(client, db_session):
    """Verify stats endpoint is rate limited"""
    from backend.shared.models import Link

    code = "statslimit"
    link = Link(codigo=code, url_original="https://example.com/stats-limit")
    db_session.add(link)
    db_session.commit()

    last_status = None
    for i in range(20):
        response = client.get(f"/api/stats/{code}")
        last_status = response.status_code
        if last_status == 429:
            break

    assert last_status == 429, (
        "Stats endpoint was never rate limited after 20 requests"
    )
