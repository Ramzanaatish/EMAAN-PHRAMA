"""SQLite models for the assistant's own database.

This database never holds POS data as its source of truth; it holds the
assistant's working copy (imported read-only from POS_DB), plus settings,
overrides, orders and the audit trail. POS_DB itself is never written to.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True, nullable=False)


class Product(Base):
    __tablename__ = "products"

    item_code = Column(String(64), primary_key=True)
    name = Column(String(256), nullable=False)
    pack = Column(String(128), default="")
    supplier = Column(String(128), default="")
    stock = Column(Integer, default=0)
    unusable = Column(Integer, default=0)
    incoming = Column(Integer, default=0)
    net_30 = Column(Integer, default=0)
    net_7 = Column(Integer, nullable=True)
    net_90 = Column(Integer, nullable=True)
    fraction_7 = Column(Float, default=0.0)
    fraction_90 = Column(Float, default=0.0)
    reorder_level = Column(Integer, default=0)
    max_level = Column(Integer, default=0)
    cost = Column(Integer, default=0)
    pack_size = Column(Integer, default=1)
    manufacturer = Column(String(128), default="")
    item_group = Column(String(128), default="")
    expiry_batch = Column(String(64), default="")
    expiry_date = Column(String(32), default="")
    expiry_qty = Column(Integer, default=0)
    expiry_key = Column(Integer, default=0)
    discontinued = Column(Boolean, default=False)
    supplier_mapped = Column(Boolean, default=True)
    data_source = Column(String(16), default="demo")  # "demo" or "live"

    overrides = relationship("Override", back_populates="product")

    def to_figures(self):
        """Plain calculation input for this product row."""
        from ..core.purchase import ItemFigures

        return ItemFigures(
            name=self.name,
            pack=self.pack,
            supplier=self.supplier,
            stock=self.stock,
            unusable=self.unusable,
            incoming=self.incoming,
            net30=self.net_30,
            fraction_7=self.fraction_7,
            fraction_90=self.fraction_90,
            reorder_level=self.reorder_level,
            max_level=self.max_level,
            cost=self.cost,
            pack_size=self.pack_size,
            item_code=self.item_code,
            manufacturer=self.manufacturer,
            item_group=self.item_group,
            expiry_batch=self.expiry_batch,
            expiry_date=self.expiry_date,
            expiry_qty=self.expiry_qty,
            expiry_key=self.expiry_key,
            discontinued=self.discontinued,
            supplier_mapped=self.supplier_mapped,
            net_7=self.net_7,
            net_90=self.net_90,
        )


class Override(Base):
    __tablename__ = "overrides"

    id = Column(Integer, primary_key=True)
    item_code = Column(String(64), ForeignKey("products.item_code"), nullable=False)
    qty = Column(Integer, nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)

    product = relationship("Product", back_populates="overrides")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, nullable=False)
    text = Column(Text, nullable=False)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True)
    status = Column(String(16), default="draft")  # draft / approved
    created_at = Column(DateTime, nullable=False)
    approved_at = Column(DateTime, nullable=True)
    total_cost = Column(Integer, default=0)

    items = relationship("PurchaseOrderItem", back_populates="order")


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False)
    item_code = Column(String(64), nullable=False)
    qty = Column(Integer, nullable=False)
    cost = Column(Integer, nullable=False)
    basis = Column(String(32), default="formula")  # formula / override

    order = relationship("PurchaseOrder", back_populates="items")


class RefreshLog(Base):
    __tablename__ = "refresh_log"

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(16), default="running")  # running / ok / failed
    rows_imported = Column(Integer, default=0)
    error = Column(Text, default="")
