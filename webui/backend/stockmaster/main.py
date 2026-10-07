"""FastAPI-Anwendung."""

from __future__ import annotations

import ipaddress
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import admin, auftraege, auth, einrichtung, freigaben, sicherung
from .config import SchluesselFehler, einstellungen
from .db import engine
from .spiel import router as spiel

log = logging.getLogger("stockmaster")

SICHERHEITS_HEADER = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
OEFFENTLICH = {"/api/auth/login", "/api/health"}


@asynccontextmanager
async def lebensdauer(_app: FastAPI):
    # Eine unbrauchbare Konfiguration verhindert den Start, statt erst bei der Anmeldung als 500 aufzufallen.
    try:
        einstellungen().schluessel_bytes()
    except SchluesselFehler as fehler:
        log.error("Konfigurationsfehler: %s", fehler)
        raise
    yield


def app_erstellen() -> FastAPI:
    e = einstellungen()
    app = FastAPI(title="StockMaster 3000", version="0.1.0", docs_url="/api/docs" if e.api_doku else None,
                  redoc_url=None, openapi_url="/api/openapi.json" if e.api_doku else None, lifespan=lebensdauer)
    netze = [ipaddress.ip_network(n) for n in e.erlaubte_netze]

    @app.middleware("http")
    async def schutz(request: Request, call_next):
        # Zweite Schranke nach dem Proxy: nur Heimnetz (Leitplanke Erreichbarkeit).
        if netze and request.client:
            try:
                adresse = ipaddress.ip_address(request.client.host)
                if not any(adresse in netz for netz in netze):
                    return JSONResponse({"detail": "Zugriff nur aus dem Heimnetz."}, status_code=403)
            except ValueError:
                return JSONResponse({"detail": "Zugriff nur aus dem Heimnetz."}, status_code=403)
        laenge = request.headers.get("content-length", "0")
        grenze = e.sicherung_max_mb * 1024 * 1024 if request.url.path == sicherung.RESTORE_PFAD else 64_000
        if laenge.isdigit() and int(laenge) > grenze:
            return JSONResponse({"detail": "Anfrage zu groß."}, status_code=413)
        antwort = await call_next(request)
        for name, wert in SICHERHEITS_HEADER.items():
            antwort.headers.setdefault(name, wert)
        return antwort

    @app.exception_handler(StarletteHTTPException)
    async def http_fehler(request: Request, exc: StarletteHTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validierung(request: Request, exc: RequestValidationError):
        felder = [".".join(str(t) for t in f.get("loc", [])[1:]) for f in exc.errors()]
        return JSONResponse({"detail": "Ungültige Eingabe.", "felder": felder}, status_code=422)

    @app.exception_handler(Exception)
    async def unerwartet(request: Request, exc: Exception):
        korrelation = uuid.uuid4().hex[:12]
        log.exception("Unerwarteter Fehler %s", korrelation)
        return JSONResponse({"detail": f"Interner Fehler (Referenz {korrelation})."}, status_code=500)

    @app.get("/api/health", response_model=None)
    def health() -> dict | JSONResponse:
        # Gesund heißt: Schlüssel gültig und Datenbank erreichbar. Einzelheiten nur im Log, nie in der Antwort.
        try:
            einstellungen().schluessel_bytes()
            with engine().connect() as verbindung:
                verbindung.execute(text("select 1"))
        except Exception as fehler:  # noqa: BLE001 - jede Störung bedeutet "nicht gesund"
            log.warning("Health-Check fehlgeschlagen: %s: %s", type(fehler).__name__, fehler)
            return JSONResponse({"ok": False}, status_code=503)
        return {"ok": True}

    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(spiel.router)
    app.include_router(einrichtung.router)
    app.include_router(auftraege.router)
    app.include_router(freigaben.router)
    app.include_router(sicherung.router)
    return app


app = app_erstellen()
