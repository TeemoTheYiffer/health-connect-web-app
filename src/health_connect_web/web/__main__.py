"""Production entrypoint for the web app: `python -m health_connect_web.web` or `hcw-web`."""

from __future__ import annotations

import os

import uvicorn


def main() -> int:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("APP_ENV", "dev").lower() not in {"prod", "production"}
    uvicorn.run(
        "health_connect_web.web.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
        # Cloud Run terminates TLS at the front-end and forwards plain HTTP with
        # X-Forwarded-Proto: https. Trust those headers so request.url_for() builds
        # https URLs (otherwise the OAuth redirect URI comes out as http://).
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
