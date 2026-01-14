from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from .models import Role, PaymentMethod, CashStatus, StockReason, PlanType


# --- Auth
class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    id: int
    tenant_id: Optional[int] = None
    role: Role
    name: str
    email: EmailStr


class AdminUserCreate(BaseModel):
    name: str = Field(min_length=2)
    email: EmailStr
    password: str = Field(min_length=6)


class TenantCreate(BaseModel):
    name: str = Field(min_length=2)
    slug: str = Field(min_length=2)
    admin_user: AdminUserCreate


class UserOut(BaseModel):
    id: int
    tenant_id: Optional[int]
    role: Role
    name: str
    email: EmailStr
    active: bool
    created_at: datetime


class TenantOut(BaseModel):
    id: int
    name: str
    slug: str

    plan: PlanType
    trial_end: datetime | None
    is_active: bool

    created_at: datetime
    updated_at: datetime

    # 👇 agregado para el front
    admin_email: str | None = None
    admin_name: str | None = None

    class Config:
        orm_mode = True


class TenantUpdateIn(BaseModel):
    is_active: bool | None = None
    plan: PlanType | None = None


# --- Users
class EmployeeCreate(BaseModel):
    name: str = Field(min_length=2)
    email: EmailStr
    password: str = Field(min_length=4)
    role: Role = Role.EMPLOYEE  # ADMIN o EMPLOYEE (controlado en router)


# --- Products

class VariantCreate(BaseModel):
    size: str
    color: str
    sku: str
    stock: int = 0
    min_stock: int = 0

class VariantOut(BaseModel):
    id: int
    size: str
    color: str
    sku: str
    stock: int
    min_stock: int

class ProductCreate(BaseModel):
    name: str = Field(min_length=2)
    category: Optional[str] = None

    # ✅ nuevos (UI)
    brand: Optional[str] = None
    description: Optional[str] = None
    size: Optional[str] = None

    sku: Optional[str] = None
    barcode: Optional[str] = None

    stock: int = 0
    min_stock: int = 0
    cost: float = 0
    price: float = 0
    active: bool = True


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None

    brand: Optional[str] = None
    description: Optional[str] = None
    size: Optional[str] = None

    sku: Optional[str] = None
    barcode: Optional[str] = None

    stock: Optional[int] = None
    min_stock: Optional[int] = None
    cost: Optional[float] = None
    price: Optional[float] = None
    active: Optional[bool] = None

class ProductOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    category: Optional[str]

    brand: Optional[str] = None
    description: Optional[str] = None
    size: Optional[str] = None

    sku: Optional[str] = None
    barcode: Optional[str] = None

    stock: int
    min_stock: int
    cost: float
    price: float
    active: bool
    created_at: datetime

    # mantenelo por compat si querés
    variants: List[VariantOut] = []

    class Config:
        from_attributes = True
    id: int
    tenant_id: int
    name: str
    category: Optional[str]

    # ✅ devolverlos al frontend
    sku: Optional[str] = None
    barcode: Optional[str] = None
    stock: int
    min_stock: int

    cost: float
    price: float
    active: bool
    created_at: datetime
    variants: List[VariantOut] = []

    class Config:
        from_attributes = True

# --- Cash
class CashOpenIn(BaseModel):
    opening_amount: float = 0


class CashCloseIn(BaseModel):
    # ✅ opcional: si no lo mandan, asumimos que el cierre = expected_amount
    counted_amount: float | None = None

    # ✅ egreso opcional antes de cerrar
    withdrawal_amount: float = 0
    withdrawal_notes: str | None = None


class CashOpenOut(BaseModel):
    id: int
    tenant_id: int
    opened_by_user_id: int
    opened_at: datetime
    opening_amount: float
    status: CashStatus

    cash_amount: float
    card_amount: float
    other_amount: float
    total_sales_amount: float
    withdrawal_amount: float
    expected_amount: float
    by_payment_method: dict

    class Config:
        from_attributes = True


class CashOut(BaseModel):
    id: int
    tenant_id: int
    opened_by_user_id: int
    opened_at: datetime
    opening_amount: float
    status: CashStatus


# --- Sales
class SaleItemIn(BaseModel):
    product_id: int
    variant_id: int
    qty: int = Field(gt=0)


class SaleCreate(BaseModel):
    payment_method: PaymentMethod
    discount: float = 0
    items: List[SaleItemIn]

class SaleItemOut(BaseModel):
    product_id: int
    variant_id: int
    name: str
    sku: str
    qty: int
    unit_price: float
    unit_cost: float


class SaleOut(BaseModel):
    id: int
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    total: float
    items_count: Optional[int] = None
    payment_method: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True  # pydantic v2
        # si estás en pydantic v1: orm_mode = True


# --- Stock
class StockAdjustIn(BaseModel):
    product_id: int
    variant_id: int
    delta: int
    note: Optional[str] = None


class StockMovementOut(BaseModel):
    id: int
    tenant_id: int
    created_at: datetime
    created_by_user_id: int
    product_id: int
    variant_id: int
    delta: int
    reason: StockReason
    note: Optional[str] = None


# --- Reports
class DashboardOut(BaseModel):
    total_sales_today: float
    total_sales_month: float
    total_products: int
    total_customers: int
    low_stock_count: int
    recent_sales: List[SaleOut]


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    cost: Optional[float] = None
    price: Optional[float] = None
    active: Optional[bool] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    stock: Optional[int] = None
    min_stock: Optional[int] = None


class VariantUpdate(BaseModel):
    size: Optional[str] = None
    color: Optional[str] = None
    sku: Optional[str] = None
    stock: Optional[int] = None
    min_stock: Optional[int] = None
