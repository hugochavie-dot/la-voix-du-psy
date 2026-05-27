"""Point d'entrée FastAPI — API + interface admin."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import router as api_router
from app.core.paths import ensure_project_dirs
from app.db.database import init_db
from app.services.fiches_exporter import FICHES_DIR, HUB_DIR, RESUMES_DIR
from app.services.questionnaires_exporter import QUESTIONNAIRES_DIR
from app.services.liner_exporter import OUTPUT_DIR as LINER_DIR
from app.services.html_exporter import OUTPUT_DIR
from app.services.source_manager import load_concepts_from_json

ADMIN_DIR = Path(__file__).parent / "admin"
templates = Jinja2Templates(directory=str(ADMIN_DIR / "templates"))
COURS_INDEX = OUTPUT_DIR / "index.html"
RESUMES_INDEX = RESUMES_DIR / "index.html"
FICHES_INDEX = FICHES_DIR / "index.html"
HUB_INDEX = HUB_DIR / "index.html"
LINER_INDEX = LINER_DIR / "README.md"
QUESTIONNAIRES_INDEX = QUESTIONNAIRES_DIR / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_project_dirs()
    init_db()
    concepts_path = Path(__file__).resolve().parents[2] / "concepts_links.json"
    if concepts_path.exists():
        from app.db.database import SessionLocal

        db = SessionLocal()
        try:
            load_concepts_from_json(db, concepts_path)
        finally:
            db.close()
    yield


app = FastAPI(
    title="Psych IA Ressources",
    description="Gestion documentaire pédagogique légale — psychologie L1/L2/L3",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api")

if (ADMIN_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=str(ADMIN_DIR / "static")), name="static")

if OUTPUT_DIR.exists() and COURS_INDEX.exists():
    app.mount("/cours", StaticFiles(directory=str(OUTPUT_DIR), html=True), name="cours")

if RESUMES_DIR.exists() and RESUMES_INDEX.exists():
    app.mount("/resumes", StaticFiles(directory=str(RESUMES_DIR), html=True), name="resumes")

if FICHES_DIR.exists() and FICHES_INDEX.exists():
    app.mount("/fiches", StaticFiles(directory=str(FICHES_DIR), html=True), name="fiches")

if HUB_DIR.exists() and HUB_INDEX.exists():
    app.mount("/hub", StaticFiles(directory=str(HUB_DIR), html=True), name="hub")

if LINER_DIR.exists() and LINER_INDEX.exists():
    app.mount("/liner", StaticFiles(directory=str(LINER_DIR), html=False), name="liner")

if QUESTIONNAIRES_DIR.exists() and QUESTIONNAIRES_INDEX.exists():
    app.mount(
        "/questionnaires",
        StaticFiles(directory=str(QUESTIONNAIRES_DIR), html=True),
        name="questionnaires",
    )


@app.get("/", response_class=HTMLResponse)
async def admin_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/accueil")
async def hub_redirect():
    if HUB_INDEX.exists():
        return RedirectResponse(url="/hub/index.html")
    return RedirectResponse(url="/")


@app.get("/cours")
async def cours_redirect():
    """Redirige vers le catalogue HTML si le site a été généré."""
    if COURS_INDEX.exists():
        return RedirectResponse(url="/cours/index.html")
    return HTMLResponse(
        "<h1>Cours HTML non générés</h1>"
        "<p>Exécutez : <code>python scripts/build_cours_html.py</code></p>"
        "<p><a href='/'>Retour à l'admin</a></p>",
        status_code=404,
    )


@app.get("/rules")
def system_rules():
    rules_path = Path(__file__).resolve().parents[2] / "config" / "system_rules.txt"
    if rules_path.exists():
        return {"rules": rules_path.read_text(encoding="utf-8")}
    return {"rules": ""}
