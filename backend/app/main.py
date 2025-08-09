# backend/app/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import List
from pydantic import BaseModel
from uuid import uuid4
from pathlib import Path
import shutil
import asyncio

# ----- slideshow config (MVP) -----
FPS = 30
SLIDE_SECONDS = 3.0         # per photo (before cross-fade starts)
XFADE_SECONDS = 0.8         # cross-fade duration between slides
ZMAX = 1.20                 # max zoom 1.0->1.20
ZINCR = (ZMAX - 1.0) / (SLIDE_SECONDS * FPS)  # per-frame zoom increment

app = FastAPI(title="Vibello API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- storage paths ---
ROOT = Path(__file__).resolve().parent.parent  # backend/
STORAGE = ROOT / "storage"
TMP_DIR = STORAGE / "tmp"
RENDERS_DIR = STORAGE / "renders"
TMP_DIR.mkdir(parents=True, exist_ok=True)
RENDERS_DIR.mkdir(parents=True, exist_ok=True)

# serve /storage/* files (so browser can download results)
app.mount("/storage", StaticFiles(directory=STORAGE), name="storage")

# --- health/version ---
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/version")
def version():
    return {"name": "vibello", "version": "0.1.0"}

# --- uploads ---
MAX_FILES = 25

def _safe_name(name: str) -> str:
    return Path(name).name.replace("\x00", "")

@app.post("/api/upload")
async def upload_images(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Limit {MAX_FILES} files.")

    job_id = str(uuid4())
    job_dir = TMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    saved, skipped = [], []
    for f in files:
        if not (f.content_type and f.content_type.startswith("image/")):
            skipped.append({"name": f.filename, "reason": "not-an-image"})
            continue
        safe = _safe_name(f.filename or "image")
        target = job_dir / safe
        with target.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append({"name": safe, "relpath": f"/storage/tmp/{job_id}/{safe}"})

    if not saved:
        try:
            job_dir.rmdir()
        except Exception:
            pass
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

# --- render skeleton ---
class RenderRequest(BaseModel):
    job_id: str  # the uploaded images job to render

# simple in-memory render state
RENDERS: dict[str, dict] = {}  # render_id -> {status, progress, job_id, output, error}

@app.post("/api/render")
async def start_render(req: RenderRequest):
    job_dir = TMP_DIR / req.job_id
    if not job_dir.exists() or not any(job_dir.iterdir()):
        raise HTTPException(status_code=404, detail="job_id not found or empty")

    render_id = str(uuid4())
    out_file = RENDERS_DIR / f"{render_id}.mp4"
    RENDERS[render_id] = {
        "status": "queued",
        "progress": 0,
        "job_id": req.job_id,
        "output": str(out_file),
        "error": None,
    }

    asyncio.create_task(_render_worker(render_id, out_file))
    return {"render_id": render_id, "status": "queued"}

@app.get("/api/render/{render_id}/status")
def render_status(render_id: str):
    info = RENDERS.get(render_id)
    if not info:
        raise HTTPException(status_code=404, detail="render_id not found")
    download_url = None
    if info["status"] == "done":
        download_url = f"/storage/renders/{Path(info['output']).name}"
    return {
        "render_id": render_id,
        "status": info["status"],
        "progress": info["progress"],
        "download_url": download_url,
        "error": info["error"],
    }

import subprocess, tempfile

async def _render_worker(render_id: str, out_file: Path):
    """Render a real slideshow: per-image Ken Burns clips -> chain with xfade."""
    try:
        RENDERS[render_id]["status"] = "processing"
        RENDERS[render_id]["progress"] = 5

        # 1) Resolve inputs (images from the job folder)
        job_id = RENDERS[render_id]["job_id"]
        job_dir = TMP_DIR / job_id
        images = sorted([p for p in job_dir.iterdir() if p.suffix.lower() in {".jpg",".jpeg",".png",".webp",".bmp"}])
        if not images:
            raise RuntimeError("No images found for this job.")

        # 2) Working temp folder for segments
        work = Path(tempfile.mkdtemp(prefix=f"render_{render_id}_", dir=str(RENDERS_DIR)))
        seg_paths: list[Path] = []
        total = len(images)

        def run_ffmpeg(args):
            return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # 3) Make one MP4 segment per image with a gentle center zoom (Ken Burns)
        frames = int(SLIDE_SECONDS * FPS)

        for idx, img in enumerate(images, start=1):
            seg = work / f"seg_{idx:03d}.mp4"

            # Fill 1280x720 by scaling UP to cover, then crop, then do a small zoom
            vf = (
                "scale=1280:720:force_original_aspect_ratio=increase,"  # fill short side
                "crop=1280:720,"                                        # trim overflow
                f"zoompan=z='min(zoom+{ZINCR:.6f},{ZMAX})':"            # gentle zoom
                "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={frames}:fps={FPS}:s=1280x720,"
                "format=yuv420p,setsar=1"
            )

            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-t", f"{SLIDE_SECONDS}",
                "-i", str(img),
                "-vf", vf,
                "-r", str(FPS),
                "-an",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                str(seg),
            ]
            res = await asyncio.to_thread(run_ffmpeg, cmd)
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg segment failed for {img.name}:\n{res.stderr[-2000:]}")
            seg_paths.append(seg)
            RENDERS[render_id]["progress"] = 5 + int(60 * idx / total)


        # 4) If only one image, just move the single segment to output
        if len(seg_paths) == 1:
            # re-encode to ensure correct pix_fmt/compat
            cmd = ["ffmpeg", "-y", "-i", str(seg_paths[0]), "-pix_fmt", "yuv420p", "-r", str(FPS), str(out_file)]
            res = await asyncio.to_thread(run_ffmpeg, cmd)
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg final failed:\n{res.stderr[:600]}")
            RENDERS[render_id]["progress"] = 100
            RENDERS[render_id]["status"] = "done"
            return

        # 5) Chain with xfade transitions
        #    offset = SLIDE_SECONDS - XFADE_SECONDS (when the fade starts)
        offset = max(SLIDE_SECONDS - XFADE_SECONDS, 0.01)
        # inputs: -i seg1 -i seg2 ...
        cmd = ["ffmpeg", "-y"]
        for p in seg_paths:
            cmd += ["-i", str(p)]

        # Build filter graph: [0:v][1:v]xfade=... [v1]; [v1][2:v]xfade=... [v2]; ...
        steps = []
        last = "[0:v]"
        for i in range(1, len(seg_paths)):
            outlbl = f"[v{i}]"
            steps.append(f"{last}[{i}:v]xfade=transition=fade:duration={XFADE_SECONDS}:offset={offset}{outlbl}")
            last = outlbl
        filtergraph = ";".join(steps)

        cmd += [
            "-filter_complex", filtergraph,
            "-map", last,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            str(out_file),
        ]

        res = await asyncio.to_thread(run_ffmpeg, cmd)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg xfade failed:\n{res.stderr[:1200]}")

        RENDERS[render_id]["progress"] = 100
        RENDERS[render_id]["status"] = "done"

    except Exception as e:
        RENDERS[render_id]["status"] = "error"
        RENDERS[render_id]["error"] = str(e) or repr(e)
