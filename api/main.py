from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.db.queries import create_tables, init_db
from api.routes.health import router as health_router
from api.routes.research import router as research_router



# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise DB on startup. Nothing to tear down on shutdown."""
    database_url = os.getenv(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./sales_agent.db"
    )
    init_db(database_url)
    await create_tables()
    print(f"[App] DB ready — {database_url}")
    yield


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Northstar Sales Agent",
    description="AI-powered sales research — contact + company intel, opportunities, email drafts",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow the React dev server and any deployed frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",
        os.getenv("FRONTEND_URL", ""),
        "https://d2hnjxvw25adze.cloudfront.net",
        "https://sales-agent.northstar.com",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(health_router)
app.include_router(research_router)


# ── Dev runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )