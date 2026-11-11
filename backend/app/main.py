import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent, alerts, auth, catalogue, dashboard, forecasts, imports, inventory
from app.api import purchase_orders, recommendations
from app.core.config import settings
from app.core.database import SessionLocal, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("inventory")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.seed_demo_data:
        from app.services.inventory_engine import run_anomaly_detection, run_recommendations
        from app.services.seed import seed_demo

        db = SessionLocal()
        try:
            started = time.perf_counter()
            seeded = seed_demo(db)
            if seeded:
                # Recommendations fall back to historical demand, so the dashboard
                # is useful immediately. Full model training is triggered by the
                # "Chạy dự báo" action in the UI (POST /api/forecasts/run).
                run_recommendations(db, tenant_id=seeded)
                run_anomaly_detection(db, tenant_id=seeded)
            logger.info("Startup preparation finished in %.1fs", time.perf_counter() - started)
        except Exception:
            logger.exception("Startup seeding failed; the API still starts with empty data.")
            db.rollback()
        finally:
            db.close()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "AI Inventory Intelligence: demand forecasting, replenishment recommendations, "
        "alerts and a human-in-the-loop agent for small retailers."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (auth, catalogue, inventory, imports, forecasts, recommendations, alerts,
               purchase_orders, agent, dashboard):
    app.include_router(module.router)


@app.get("/api/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


@app.get("/health", include_in_schema=False)
def health_alias() -> dict:
    """Alias used by simple container/orchestrator health checks."""
    return health()


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "app": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }
