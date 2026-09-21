"""Unit tests for SIWE message construction (no DB required)."""
import datetime as dt

from app.services.auth import build_siwe_message


def test_message_contains_address_and_nonce():
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)
    msg = build_siwe_message("0xabc123", "deadbeef", expires)
    assert "0xabc123" in msg
    assert "deadbeef" in msg
    assert "does not authorize any transaction" in msg
