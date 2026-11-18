"""Tests for server-address validation and bundled-asset paths."""

from __future__ import annotations

import sys

import pytest

from app.core.config import resource_path, validate_server_address


@pytest.mark.parametrize(
    "address",
    [
        "localhost",
        r"localhost\SQLEXPRESS",
        "192.168.1.10",
        r"192.168.1.10\SQLEXPRESS",
        "DBHOST,1433",
        r"DBHOST\SQL2019,1433",
        "  localhost  ",
    ],
)
def test_validate_server_address_accepts(address):
    assert validate_server_address(address) == address.strip()


@pytest.mark.parametrize(
    "address",
    [
        "",
        "   ",
        "bad server!",
        "server\\",
        "server,0",
        "server,99999",
        "server,,1433",
        "server\\INSTANCE\\EXTRA",
    ],
)
def test_validate_server_address_rejects(address):
    with pytest.raises(ValueError):
        validate_server_address(address)


def test_resource_path_finds_light_logo():
    path = resource_path("eman-logo-light.png")
    assert path.name == "eman-logo-light.png"
    assert path.is_file()


def test_resource_path_frozen_uses_meipass(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert resource_path("eman-logo-light.png") == (
        tmp_path / "assets" / "eman-logo-light.png"
    )
