from fastapi import FastAPI
from .db import engine, Base, SessionLocal
from .seed import ensure_seed

from .routers.auth import router as auth_router
from .routers.tenants import router as tenants_router
from .routers.users import router as users_router
from .routers.products import router as products_router
from .routers.cash import router as cash_router
from .routers.sales import router as sales_router
from .routers.stock import router as stock_router
from .routers.reports import router as reports_router

app = FastAPI(title="BoutiqueOS API")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_seed(db)
    finally:
        db.close()


from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(tenants_router)
app.include_router(users_router)
app.include_router(products_router)
app.include_router(cash_router)
app.include_router(sales_router)
app.include_router(stock_router)
app.include_router(reports_router)


@app.get("/health")
def health():
    return {"ok": True}
