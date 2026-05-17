"""FastAPI application factory and routes."""

from __future__ import annotations

import logging
from importlib.resources import files
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from health_connect_web import __version__
from health_connect_web.config import get_settings
from health_connect_web.db import get_db
from health_connect_web.models import create_all
from health_connect_web.web import auth, content, exports, queries

log = logging.getLogger(__name__)


def _package_dir() -> Path:
    """Locate `health_connect_web` package on disk (works in editable & wheel installs)."""
    return Path(str(files("health_connect_web")))


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    pkg = _package_dir()
    templates = Jinja2Templates(directory=str(pkg / "templates"))
    templates.env.globals["app_version"] = __version__

    app = FastAPI(title="Health Portfolio", version=__version__, docs_url=None, redoc_url=None)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        https_only=settings.is_prod,
        same_site="lax",
    )
    app.mount("/static", StaticFiles(directory=str(pkg / "static")), name="static")

    # Ensure tables exist. Safe in dev; in prod, prefer running `hcw-sync --init-db` once first.
    create_all()

    @app.exception_handler(FastAPIHTTPException)
    async def _redirect_303(request: Request, exc: FastAPIHTTPException):
        # Honor the redirect-via-303 trick from auth.require_user.
        if exc.status_code == 303 and "Location" in (exc.headers or {}):
            return RedirectResponse(url=exc.headers["Location"], status_code=303)
        # Default behavior for everything else.
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)

    # ---- Public auth routes ----

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request, error: str | None = None):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": error, "user": None},
        )

    @app.get("/auth/google")
    async def auth_google(request: Request):
        return await auth.login_redirect(request)

    @app.get("/auth/callback", name="auth_callback")
    async def auth_callback(request: Request):
        return await auth.handle_callback(request)

    @app.get("/logout")
    async def logout(request: Request):
        return auth.logout(request)

    @app.get("/forbidden", response_class=HTMLResponse)
    async def forbidden(request: Request):
        pending = request.session.get("pending_user")
        return templates.TemplateResponse(
            request,
            "forbidden.html",
            {"pending_user": pending, "user": None},
            status_code=403,
        )

    @app.get("/healthz")
    async def healthz():
        return {"ok": True, "version": __version__}

    # ---- Auth-gated JSON APIs (used by chart dropdowns to refetch without page reload) ----

    @app.get("/api/food/macros")
    async def api_food_macros(
        days: int = 14,
        user: dict = Depends(auth.require_user),
        db: Session = Depends(get_db),
    ):
        days = max(1, min(int(days), 365))  # clamp to a sane range
        daily = queries.daily_nutrition(db, days=days)
        return {"days": days, "chart": queries.food_chart_data(daily)}

    @app.get("/api/health/{chart}")
    async def api_health_chart(
        chart: str,
        days: int = 7,
        user: dict = Depends(auth.require_user),
        db: Session = Depends(get_db),
    ):
        _ = user  # auth gate only
        days = max(1, min(int(days), 365))
        builder = queries.HEALTH_CHART_BUILDERS.get(chart)
        if builder is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail=f"Unknown chart: {chart}")
        return {"chart": chart, "days": days, "data": builder(db, days=days)}

    # ---- Authenticated pages ----

    @app.get("/", response_class=HTMLResponse, name="index")
    async def index(
        request: Request,
        user: dict = Depends(auth.require_user),
        db: Session = Depends(get_db),
    ):
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "user": user,
                "summary": queries.landing_summary(db),
                "combined_micros": queries.combined_daily_intake(db, food_days=7),
            },
        )

    @app.get("/health", response_class=HTMLResponse, name="page_health")
    async def page_health(
        request: Request,
        user: dict = Depends(auth.require_user),
        db: Session = Depends(get_db),
    ):
        return templates.TemplateResponse(
            request,
            "health.html",
            {
                "user": user,
                "bp_latest": queries.latest_blood_pressure(db),
                "weight_latest": queries.latest_weight(db),
                "body_fat": queries.latest_body_fat(db),
                "height": queries.latest_height(db),
                "exercise_recent": queries.recent_exercise_sessions(db, limit=12),
                "sleep_recent": queries.recent_sleep_sessions(db, days=30),
                "charts": queries.health_chart_data(db),
            },
        )

    @app.get("/food", response_class=HTMLResponse, name="page_food")
    async def page_food(
        request: Request,
        user: dict = Depends(auth.require_user),
        db: Session = Depends(get_db),
    ):
        daily = queries.daily_nutrition(db, days=14)
        return templates.TemplateResponse(
            request,
            "food.html",
            {
                "user": user,
                "daily": daily,
                "macros_chart": queries.food_chart_data(daily),
                "micros_avg": queries.micronutrient_averages(db, days=7),
                "top_meals": queries.top_meals(db, days=30, limit=15),
                "latest_log_at": queries.latest_nutrition_at(db),
            },
        )

    @app.get("/export.md", name="export_markdown")
    async def export_markdown(
        user: dict = Depends(auth.require_user),
        db: Session = Depends(get_db),
    ):
        _ = user  # auth gate only
        content = exports.build_export_markdown(db)
        from datetime import date

        from fastapi.responses import Response

        return Response(
            content,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="health-portfolio-{date.today()}.md"',
            },
        )

    @app.get("/data", response_class=HTMLResponse, name="page_data")
    async def page_data(
        request: Request,
        user: dict = Depends(auth.require_user),
        db: Session = Depends(get_db),
    ):
        return templates.TemplateResponse(
            request,
            "data.html",
            {
                "user": user,
                "summary": queries.landing_summary(db),
                "freshness": queries.data_freshness(db),
                "recent_runs": queries.recent_sync_runs(db, limit=10),
            },
        )

    @app.get("/teas", response_class=HTMLResponse, name="page_teas")
    async def page_teas(
        request: Request,
        user: dict = Depends(auth.require_user),
        db: Session = Depends(get_db),
    ):
        return templates.TemplateResponse(
            request,
            "teas.html",
            {
                "user": user,
                "herbs": queries.herbs(db),
                "brewing": content.tea_brewing(),
            },
        )

    @app.get("/schedule", response_class=HTMLResponse, name="page_schedule")
    async def page_schedule(
        request: Request,
        user: dict = Depends(auth.require_user),
    ):
        return templates.TemplateResponse(
            request,
            "schedule.html",
            {"user": user, "data": content.schedule_data()},
        )

    @app.get("/supplements", response_class=HTMLResponse, name="page_supplements")
    async def page_supplements(
        request: Request,
        user: dict = Depends(auth.require_user),
        db: Session = Depends(get_db),
    ):
        return templates.TemplateResponse(
            request,
            "supplements.html",
            {
                "user": user,
                "items": queries.vitamins(db),
                "dv_tally": queries.supplement_dv_tally(db),
            },
        )

    # Old route name is kept (redirect-only) for any bookmarks.
    @app.get("/vitamins")
    async def vitamins_redirect():
        return RedirectResponse(url="/supplements", status_code=308)

    return app


# Module-level instance for `uvicorn health_connect_web.web.app:app`
app = create_app()
