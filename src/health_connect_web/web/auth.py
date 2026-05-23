"""Google OAuth + email-allowlist gate for the web app.

Flow:
- /login renders a "sign in with Google" page.
- /auth/google redirects to Google.
- /auth/callback receives the auth code, fetches the userinfo, validates email is
  in ALLOWED_EMAILS (or matches OWNER_EMAIL), stores user in the session cookie.
- A FastAPI dependency `require_user` gates every page; otherwise redirects to /login,
  except for users with valid Google identity but disallowed email -> /forbidden.
"""

from __future__ import annotations

import logging
from typing import Any

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from health_connect_web.config import Settings, get_settings

log = logging.getLogger(__name__)

_oauth: OAuth | None = None


def get_oauth(settings: Settings | None = None) -> OAuth:
    global _oauth
    if _oauth is None:
        s = settings or get_settings()
        oauth = OAuth()
        oauth.register(
            name="google",
            client_id=s.google_oauth_client_id,
            client_secret=s.google_oauth_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        _oauth = oauth
    return _oauth


def current_user(request: Request) -> dict[str, Any] | None:
    return request.session.get("user")


def require_user(request: Request) -> dict[str, Any]:
    """Dependency: returns the signed-in user dict, or raises an HTTP redirect."""
    user = current_user(request)
    if not user:
        # 307 keeps the method, but for GETs that's irrelevant; FastAPI's HTTPException
        # with redirect won't preserve URL state, so use a sentinel header instead.
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return user


def require_owner(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    s = get_settings()
    if user.get("email", "").lower() != s.owner_email.strip().lower():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return user


def _is_email_allowed(email: str) -> bool:
    """Owner is always allowed. Then we union the env-var allowlist (config fallback)
    with the DB allowlist managed via /admin. Using a fresh session_scope so this
    runs in the OAuth callback without needing FastAPI's Depends machinery.
    """
    s = get_settings()
    e = email.strip().lower()
    if not e:
        return False
    if s.owner_email.strip().lower() == e:
        return True
    if e in s.allowed_emails_list:
        return True
    # DB-managed allowlist.
    from health_connect_web.db import session_scope
    from health_connect_web.web.queries import is_email_in_db_allowlist

    with session_scope() as db:
        return is_email_in_db_allowlist(db, e)


async def login_redirect(request: Request) -> RedirectResponse:
    redirect_uri = request.url_for("auth_callback")
    return await get_oauth().google.authorize_redirect(request, str(redirect_uri))


async def handle_callback(request: Request) -> RedirectResponse:
    try:
        token = await get_oauth().google.authorize_access_token(request)
    except OAuthError as e:
        log.warning("OAuth error: %s", e)
        return RedirectResponse(url="/login?error=oauth", status_code=status.HTTP_303_SEE_OTHER)

    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or "").lower()
    name = userinfo.get("name") or email
    picture = userinfo.get("picture")

    if not email or not userinfo.get("email_verified", True):
        return RedirectResponse(url="/login?error=email", status_code=status.HTTP_303_SEE_OTHER)

    if not _is_email_allowed(email):
        # Stash a minimal identity to render the friendly /forbidden page.
        request.session["pending_user"] = {"email": email, "name": name}
        return RedirectResponse(url="/forbidden", status_code=status.HTTP_303_SEE_OTHER)

    request.session["user"] = {"email": email, "name": name, "picture": picture}
    request.session.pop("pending_user", None)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
