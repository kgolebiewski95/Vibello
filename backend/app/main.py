# backend/app/main.py
from __future__ import annotations

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import asyncio
import shutil
import subprocess
import tempfile
import uuid

# =========================
# Config (defaults; overridable in /api/render)
# =========================
APP_NAME = "Vibello API"
APP_VERSION = "0.2.1"

CORS_ORIGINS = ["http://localhost:5173"]

FPS_DEFAULT = 30
SLIDE_SECONDS_DEFAULT = 3.0
XFADE_SECONDS_DEFAULT = 0.8

FREE_TIER = True
WATERMARK_TEXT = "Made with Vibello"

MAX_FILES = 25
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# Paths
ROOT = Path(__file__).resolve().parent.parent      # backend/
STORAGE = ROOT / "storage"
TMP_DIR = STORAGE / "tmp"
RENDERS_DIR = STORAGE / "renders"
ASSETS_DIR = ROOT / "assets"
MUSIC_FILE = ASSETS_DIR / "music" / "default.mp3"

TMP_DIR.mkdir(parents=True, exist_ok=True)
RENDERS_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# =========================
# App
# =========================
app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/storage", StaticFiles(directory=STORAGE), name="storage")

# =========================
# Health
# =========================
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/version")
def version():
    return {"name": "vibello", "version": APP_VERSION}

# =========================
# Upload
# =========================
def _safe_name(name: str) -> str:
    return Path(name or "image").name.replace("\x00", "")

@app.post("/api/upload")
async def upload_images(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Limit {MAX_FILES} files.")

    job_id = str(uuid.uuid4())
    job_dir = TMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    saved, skipped = [], []
    for f in files:
        if not (f.content_type and f.content_type.startswith("image/")):
            skipped.append({"name": f.filename, "reason": "not-an-image"})
            continue
        safe = _safe_name(f.filename)
        with (job_dir / safe).open("wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append({"name": safe, "relpath": f"/storage/tmp/{job_id}/{safe}"})

    if not saved:
        try: job_dir.rmdir()
        except Exception: pass
        raise HTTPException(status_code=400, detail="No valid image files.")

    return {"job_id": job_id, "saved_count": len(saved), "skipped_count": len(skipped),
            "saved": saved, "skipped": skipped}

@app.get("/api/job/{job_id}")
def get_job(job_id: str):
    job_dir = TMP_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job_id not found")
    files = sorted(p.name for p in job_dir.iterdir() if p.is_file())
    return {"job_id": job_id, "files": files}

# =========================
# Render API
# =========================
class RenderRequest(BaseModel):
    job_id: str
    slide_seconds: Optional[float] = None
    xfade_seconds: Optional[float] = None
    fps: Optional[int] = None

RENDERS: dict[str, dict] = {}  # render_id -> {status, progress, job_id, output, error, cfg}

@app.post("/api/render")
async def start_render(req: RenderRequest):
    job_dir = TMP_DIR / req.job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job_id not found")

    images = [p for p in job_dir.iterdir() if p.suffix.lower() in ALLOWED_EXTS]
    if not images:
        raise HTTPException(status_code=400, detail="No images found for this job_id")

    fps = max(12, min(60, int(req.fps or FPS_DEFAULT)))
    slide_s = max(1.0, min(12.0, float(req.slide_seconds or SLIDE_SECONDS_DEFAULT)))
    xfade_s = float(req.xfade_seconds or XFADE_SECONDS_DEFAULT)
    xfade_s = max(0.2, min(slide_s - 0.1, xfade_s))  # must be shorter than slide

    render_id = str(uuid.uuid4())
    out_file = RENDERS_DIR / f"{render_id}.mp4"
    RENDERS[render_id] = {
        "status": "queued",
        "progress": 0,
        "job_id": req.job_id,
        "output": str(out_file),
        "error": None,
        "cfg": {"fps": fps, "slide_s": slide_s, "xfade_s": xfade_s},
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
    return {"render_id": render_id, "status": info["status"], "progress": info["progress"],
            "download_url": download_url, "error": info["error"]}

# =========================
# Helper funcs
# =========================
def _run(args: list[str]):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def _dominant_color(image_path: Path) -> tuple[int,int,int]:
    """Fast approximate dominant color (average of downscaled image)."""
    try:
        from PIL import Image, ImageStat
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            im = im.resize((50, 50))
            r, g, b = [int(x) for x in ImageStat.Stat(im).mean]
            return r, g, b
    except Exception:
        return (168, 134, 221)  # fallback lavender

def _radial_gradient_png(size: tuple[int,int], center_color: tuple[int,int,int], out_path: Path):
    """Create a radial gradient PNG (center color -> darker edge)."""
    from math import hypot
    from PIL import Image

    w, h = size
    cx, cy = w / 2.0, h / 2.0
    maxd = ( (w/2.0)**2 + (h/2.0)**2 ) ** 0.5

    # Precompute darker edge color (~40% of center)
    edge = tuple(max(0, int(c * 0.40)) for c in center_color)

    # Build three channels separately for speed
    r0, g0, b0 = center_color
    r1, g1, b1 = edge

    # Create blank image
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = min(1.0, hypot(x - cx, y - cy) / maxd)  # 0 center -> 1 edge
            # linear blend
            r = int(r0 * (1 - t) + r1 * t)
            g = int(g0 * (1 - t) + g1 * t)
            b = int(b0 * (1 - t) + b1 * t)
            px[x, y] = (r, g, b)
    img.save(out_path)

# =========================
# Render worker (Option C: gradient background)
# =========================
async def _render_worker(render_id: str, out_file: Path):
    """
    For each photo:
      - Build a 1280x720 radial-gradient background from its dominant color.
      - Scale the photo to FIT inside 1280x720 (no crop, no stretch, no upscale above source).
      - Center the photo over the gradient.
    Then:
      - Chain with xfade (increasing offsets).
      - Add music + PNG watermark.
    """
    try:
        info = RENDERS[render_id]
        info["status"] = "processing"; info["progress"] = 5
        cfg = info["cfg"]; fps = cfg["fps"]; SLIDE = cfg["slide_s"]; XFADE = cfg["xfade_s"]

        job_dir = TMP_DIR / info["job_id"]
        images = sorted([p for p in job_dir.iterdir() if p.suffix.lower() in ALLOWED_EXTS],
                        key=lambda p: p.name.lower())
        if not images:
            raise RuntimeError("No images found for this job.")

        work = Path(tempfile.mkdtemp(prefix=f"render_{render_id}_", dir=str(RENDERS_DIR)))
        segs: list[Path] = []

        # --- 1) Per-image segments (gradient bg + fit foreground) ---
        for idx, img in enumerate(images, start=1):
            seg = work / f"seg_{idx:03d}.mp4"
            bg = work / f"bg_{idx:03d}.png"

            # Make gradient background
            base = _dominant_color(img)
            _radial_gradient_png((1280, 720), base, bg)

            # Two inputs: bg then foreground photo
            # - Loop each for SLIDE seconds
            # - Scale fg to fit (no upscale), then overlay centered onto bg
            vf = (
                "[1:v]scale=w='min(iw,1280)':h='min(ih,720)':force_original_aspect_ratio=decrease[fg];"
                "[0:v][fg]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2,"
                f"fps={fps},format=yuv420p,setsar=1[v]"
            )
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-t", f"{SLIDE}", "-i", str(bg),
                "-loop", "1", "-t", f"{SLIDE}", "-i", str(img),
                "-filter_complex", vf, "-map", "[v]",
                "-r", str(fps), "-an",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                str(seg),
            ]
            r = await asyncio.to_thread(_run, cmd)
            if r.returncode != 0:
                raise RuntimeError(f"FFmpeg segment failed for {img.name}:\n{r.stderr[-1500:]}")

            segs.append(seg)
            info["progress"] = 5 + int(60 * idx / max(len(images), 1))

        # --- 2) Stitch with xfade (increasing offsets) ---
        if len(segs) == 1:
            cmd = ["ffmpeg", "-y", "-i", str(segs[0]),
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                   "-pix_fmt", "yuv420p", str(out_file)]
            r = await asyncio.to_thread(_run, cmd)
            if r.returncode != 0:
                raise RuntimeError(f"FFmpeg final (single) failed:\n{r.stderr[-1500:]}")
        else:
            cmd = ["ffmpeg", "-y"]
            for p in segs: cmd += ["-i", str(p)]
            steps = []
            last = "[0:v]"
            for i in range(1, len(segs)):
                outlbl = f"[v{i}]"
                offset = i * (SLIDE - XFADE)
                steps.append(
                    f"{last}[{i}:v]xfade=transition=fade:duration={XFADE}:offset={offset:.3f},"
                    "format=yuv420p" + outlbl
                )
                last = outlbl
            filtergraph = ";".join(steps)
            cmd += ["-filter_complex", filtergraph, "-map", last,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-pix_fmt", "yuv420p", str(out_file)]
            r = await asyncio.to_thread(_run, cmd)
            if r.returncode != 0:
                raise RuntimeError(f"FFmpeg xfade failed:\n{r.stderr[-2000:]}")

        # --- 3) Music + PNG watermark (same as before) ---
        video_only = out_file.with_suffix(".video.mp4")
        out_file.rename(video_only)
        final_out = out_file

        N = len(segs)
        total_seconds = max(N * SLIDE - (N - 1) * XFADE, 0.5)
        fade_out_start = max(total_seconds - 0.8, 0.0)

        # Make small watermark PNG on the fly
        wm_path = None
        if FREE_TIER:
            try:
                from PIL import Image, ImageDraw, ImageFont
                W, H = 420, 56
                im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                d = ImageDraw.Draw(im)
                d.rounded_rectangle([0, 0, W, H], radius=12, fill=(0, 0, 0, int(255 * 0.30)))
                try:
                    font = ImageFont.truetype("arial.ttf", 28)
                except Exception:
                    font = ImageFont.load_default()
                d.text((16, 14), WATERMARK_TEXT, fill=(255, 255, 255, int(255 * 0.85)), font=font)
                wm_path = RENDERS_DIR / f"{render_id}_wm.png"
                im.save(wm_path)
            except Exception:
                wm_path = None

        if MUSIC_FILE.exists() and wm_path:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_only), "-stream_loop", "-1", "-i", str(MUSIC_FILE), "-i", str(wm_path),
                "-shortest",
                "-filter_complex", "[0:v][2:v]overlay=main_w-overlay_w-24:main_h-overlay_h-24[v]",
                "-map", "[v]", "-map", "1:a",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-af", f"afade=t=in:st=0:d=0.5,afade=t=out:st={fade_out_start:.2f}:d=0.8",
                str(final_out),
            ]
        elif MUSIC_FILE.exists():
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_only), "-stream_loop", "-1", "-i", str(MUSIC_FILE),
                "-shortest",
                "-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-af", f"afade=t=in:st=0:d=0.5,afade=t=out:st={fade_out_start:.2f}:d=0.8",
                str(final_out),
            ]
        elif wm_path:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_only), "-i", str(wm_path),
                "-filter_complex", "[0:v][1:v]overlay=main_w-overlay_w-24:main_h-overlay_h-24[v]",
                "-map", "[v]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                str(final_out),
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-i", str(video_only),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                str(final_out),
            ]
        r = await asyncio.to_thread(_run, cmd)
        if r.returncode != 0:
            raise RuntimeError(f"Audio/overlay failed:\n{r.stderr[-1500:]}")

        # Cleanup
        try: video_only.unlink(missing_ok=True)
        except Exception: pass
        try:
            if 'wm_path' in locals() and wm_path:
                Path(wm_path).unlink(missing_ok=True)
        except Exception:
            pass

        info["progress"] = 100; info["status"] = "done"

    except Exception as e:
        RENDERS[render_id]["status"] = "error"
        RENDERS[render_id]["error"] = str(e) or repr(e)
