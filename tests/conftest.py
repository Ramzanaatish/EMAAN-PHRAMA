"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from app.database.seed import DEMO_ITEMS, seed_demo_data
from app.database.store import Store


@pytest.fixture()
def store(tmp_path):
    """A fresh store (temporary SQLite file) for each test."""
    return Store(tmp_path / "test.db")


@pytest.fixture()
def demo_store(store):
    """A store seeded with the 18 demo items, demo data on."""
    seed_demo_data(store)
    return store


@pytest.fixture()
def panadol():
    return next(item for item in DEMO_ITEMS if item.name == "Panadol Extra 500mg")


@pytest.fixture()
def brufen():
    return next(item for item in DEMO_ITEMS if item.name == "Brufen 400mg")


@pytest.fixture()
def augmentin():
    return next(item for item in DEMO_ITEMS if item.name == "Augmentin 625mg")
