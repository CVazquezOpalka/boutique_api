import enum
from datetime import datetime
from sqlalchemy import (
    String, Integer, DateTime, Enum, Boolean, ForeignKey, Float,
    UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class PlanType(str, enum.Enum):
    FREE_TRIAL = "FREE_TRIAL"
    MONTHLY = "MONTHLY"
    SEMESTER = "SEMESTER"
    ANNUAL = "ANNUAL"

class Role(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    EMPLOYEE = "EMPLOYEE"

class PaymentMethod(str, enum.Enum):
    EFECTIVO = "EFECTIVO"
    DEBITO = "DEBITO"
    CREDITO = "CREDITO"
    TRANSFERENCIA = "TRANSFERENCIA"

class CashStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"

class StockReason(str, enum.Enum):
    VENTA = "VENTA"
    AJUSTE = "AJUSTE"
    INGRESO = "INGRESO"
    EGRESO = "EGRESO"
    RESERVA = "RESERVA"

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    jti: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user = relationship("User")

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    plan: Mapped[PlanType] = mapped_column(
        Enum(PlanType),
        default=PlanType.FREE_TRIAL,
        nullable=False,
    )

    trial_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    users: Mapped[list["User"]] = relationship(back_populates="tenant")

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_tenant_role", "tenant_id", "role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=True)  # null = superadmin
    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tenant: Mapped["Tenant"] = relationship(back_populates="users")

class Product(Base):
    __tablename__ = "products"
    __table_args__ = (Index("ix_products_tenant", "tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)

    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)

    # ✅ NUEVO
    sku: Mapped[str | None] = mapped_column(String, nullable=True)
    barcode: Mapped[str | None] = mapped_column(String, nullable=True)

    cost: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    price: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    # ✅ NUEVO (stock simple para MVP)
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    variants: Mapped[list["Variant"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan"
    )
    
class Variant(Base):
    __tablename__ = "variants"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_variants_tenant_sku"),
        Index("ix_variants_tenant", "tenant_id"),
        Index("ix_variants_product", "product_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)
    size: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[str] = mapped_column(String, nullable=False)
    sku: Mapped[str] = mapped_column(String, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="variants")

class CashSession(Base):
    __tablename__ = "cash_sessions"
    __table_args__ = (Index("ix_cash_tenant_status", "tenant_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    opened_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    opening_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    status: Mapped[CashStatus] = mapped_column(Enum(CashStatus), default=CashStatus.OPEN, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closing_amount: Mapped[float | None] = mapped_column(Float, nullable=True)

class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (Index("ix_sales_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    payment_method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod), nullable=False)
    discount: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    subtotal: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    total: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    margin: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    cash_session_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("cash_sessions.id"), nullable=True)

    items: Mapped[list["SaleItem"]] = relationship(back_populates="sale", cascade="all, delete-orphan")

class SaleItem(Base):
    __tablename__ = "sale_items"
    __table_args__ = (Index("ix_sale_items_sale", "sale_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sale_id: Mapped[int] = mapped_column(Integer, ForeignKey("sales.id"), nullable=False)

    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    variant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    sku: Mapped[str] = mapped_column(String, nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False)

    sale: Mapped["Sale"] = relationship(back_populates="items")

class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (Index("ix_stock_mov_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    variant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[StockReason] = mapped_column(Enum(StockReason), nullable=False)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
