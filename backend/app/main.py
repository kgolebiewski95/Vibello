# backend/app/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from uuid import uuid4
from pathlib import Path
import shutil

app = FastAPI(title="Vibello API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- health/version ---
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/version")
def version():
    return {"name": "vibello", "version": "0.1.0"}

# --- upload storage paths ---
ROOT = Path(__file__).resolve().parent.parent  # backend/
STORAGE = ROOT / "storage"
TMP_DIR = STORAGE / "tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILES = 25

# --- helpers ---
def _safe_name(name: str) -> str:
    # strip any directory parts; keep just the filename
    return Path(name).name.replace("\x00", "")

# --- endpoints ---
@app.post("/api/upload")
async def upload_images(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Limit {MAX_FILES} files.")

    job_id = str(uuid4())
    job_dir = TMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    skipped = []
    for f in files:
        if not (f.content_type and f.content_type.startswith("image/")):
            skipped.append({"name": f.filename, "reason": "not-an-image"})
            continue

        safe = _safe_name(f.filename or "image")
        target = job_dir / safe

        with target.open("wb") as out:
            # stream-copy to disk
            shutil.copyfileobj(f.file, out)

        saved.append({"name": safe, "relpath": f"/storage/tmp/{job_id}/{safe}"})

    if not saved:
        # cleanup empty folder
        try: job_dir.rmdir()
        except Exception: pass
        raise HTTPException(status_code=400, detail="No valid image files.")

    return {
        "job_id": job_id,
        "saved_count": len(saved),
        "skipped_count": len(skipped),
        "saved": saved,
        "skipped": skipped,
    }

@app.get("/api/job/{job_id}")
def get_job(job_id: str):
    job_dir = TMP_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job_id not found")
    files = sorted(p.name for p in job_dir.iterdir() if p.is_file())
    return {"job_id": job_id, "files": files}
