"""POS connector interface.

A connector only ever reads from the POS database. The interface is
deliberately narrow: inspect the schema, fetch product/stock/sales rows.
There is no write method anywhere in this layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class PosConnector(ABC):
    """Read-only source of POS data."""

    @abstractmethod
    def test_connection(self) -> str:
        """Return a short human-readable connection summary or raise."""

    @abstractmethod
    def list_columns(self, table_name: str) -> list[str]:
        """Column names of a POS table or view, in ordinal order."""

    @abstractmethod
    def fetch_products(self) -> list[dict]:
        """One row per ItemInfo record with the verified columns."""

    @abstractmethod
    def fetch_stock(self) -> list[dict]:
        """Current stock rows from the ItemStock view."""

    @abstractmethod
    def fetch_sales(self, days: int) -> list[dict]:
        """Net sales per item for the last `days` days (returns excluded)."""
