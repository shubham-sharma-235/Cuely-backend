from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.db.session import engine
from app.db.base import Base
from app.utils.limiter import ip_limiter, user_limiter
from app.routers import auth, tables, menu, sessions, bookings, lenders, analytics

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="CueManager API",
    version="1.0.0",
    description="Multi-tenant billiards club management backend",
)

# ── Rate limiting ─────────────────────────────────────────────────────────
# We mount the IP limiter as the primary (it covers unauthenticated routes).
# Authenticated routes use user_limiter decorators in their routers.
app.state.limiter = ip_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── CORS ──────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(tables.router)
app.include_router(menu.router)
app.include_router(sessions.router)
app.include_router(bookings.router)
app.include_router(lenders.router)
app.include_router(analytics.router)


@app.get("/health")
def health():
    return {"status": "ok"}