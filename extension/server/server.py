from __future__ import annotations

import json
import mimetypes
import shutil
import tempfile
import threading
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote

import yt_dlp


HOST = "0.0.0.0"
PORT = 8765

# Files are downloaded into a per-job staging dir, streamed to the client,
# then removed. STAGING_BASE holds all live job directories.
STAGING_BASE = Path(tempfile.gettempdir()) / "ytmp3dl"

# Downloads run in background threads; JOBS holds their live state.
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def job_dir(job_id: str) -> Path:
    return STAGING_BASE / job_id


def build_ydl_opts(params: dict, job: dict, out_dir: Path) -> dict:
    fmt = params.get("format") or "mp3"
    quality = str(params.get("quality") or 320)
    noplaylist = bool(params.get("noplaylist", False))

    outtmpl = str(out_dir / "%(channel,uploader,creator)s" / "%(title)s.%(ext)s")

    def progress_hook(d: dict) -> None:
        status = d.get("status")
        if status == "downloading":
            info = d.get("info_dict") or {}
            with JOBS_LOCK:
                job["stage"] = "downloading"
                job["current_title"] = info.get("title") or d.get("filename")
                job["percent"] = (d.get("_percent_str") or "").strip()
                if info.get("playlist_title"):
                    job["playlist_title"] = info["playlist_title"]
        elif status == "finished":
            with JOBS_LOCK:
                job["stage"] = "converting"

    def postprocessor_hook(d: dict) -> None:
        if d.get("status") == "finished" and d.get("postprocessor") == "MoveFiles":
            with JOBS_LOCK:
                job["completed"] = job.get("completed", 0) + 1

    out_dir.mkdir(parents=True, exist_ok=True)

    return {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "restrictfilenames": False,
        "ignoreerrors": True,
        "writethumbnail": False,
        "noplaylist": noplaylist,
        "quiet": True,
        "no_warnings": True,
        "js_runtimes": {"deno": {}, "node": {}},
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [postprocessor_hook],
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": fmt,
                "preferredquality": quality,
            },
            {"key": "FFmpegMetadata"},
        ],
    }


def do_download(job_id: str, params: dict) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["status"] = "running"
    out_dir = job_dir(job_id)
    try:
        opts = build_ydl_opts(params, job, out_dir)
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([params["url"]])
        files = [
            str(p)
            for p in sorted(out_dir.rglob("*"))
            if p.is_file() and not p.name.endswith(".part")
        ]
        with JOBS_LOCK:
            job["files"] = files
            if not files:
                job["status"] = "error"
                job["error"] = "No files produced (check URL / ffmpeg)."
            else:
                job["status"] = "done"
                job["stage"] = "done"
    except Exception as exc:  # noqa: BLE001 - surface any yt-dlp failure to the client
        with JOBS_LOCK:
            job["status"] = "error"
            job["error"] = str(exc)


def cleanup_job(job_id: str) -> None:
    shutil.rmtree(job_dir(job_id), ignore_errors=True)
    zip_path = STAGING_BASE / f"{job_id}.zip"
    if zip_path.exists():
        zip_path.unlink(missing_ok=True)
    with JOBS_LOCK:
        JOBS.pop(job_id, None)


def content_disposition(filename: str) -> str:
    ascii_name = filename.encode("ascii", "ignore").decode() or "download"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def public_state(job: dict) -> dict:
    keys = ("id", "status", "stage", "completed", "current_title", "percent", "error")
    return {k: job.get(k) for k in keys}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # noqa: N802 - keep server output quiet
        pass

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream_file(self, path: Path, download_name: str) -> bool:
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        try:
            size = path.stat().st_size
            with path.open("rb") as fh:
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(size))
                self.send_header("Content-Disposition", content_disposition(download_name))
                self._cors()
                self.end_headers()
                shutil.copyfileobj(fh, self.wfile)
            return True
        except (OSError, ConnectionError):
            return False

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/health":
            self._send_json(200, {"status": "ok", "yt_dlp": yt_dlp.version.__version__})
            return

        if parsed.path == "/status":
            job_id = (query.get("id") or [""])[0]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                payload = public_state(job) if job else None
            if payload is None:
                self._send_json(404, {"error": "unknown job id"})
            else:
                self._send_json(200, payload)
            return

        if parsed.path == "/file":
            self._handle_file(query)
            return

        self._send_json(404, {"error": "not found"})

    def _handle_file(self, query: dict) -> None:
        job_id = (query.get("id") or [""])[0]
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            status = job.get("status") if job else None
            files = list(job.get("files") or []) if job else []
            playlist_title = job.get("playlist_title") if job else None
        if job is None:
            self._send_json(404, {"error": "unknown job id"})
            return
        if status != "done" or not files:
            self._send_json(409, {"error": "not ready"})
            return

        if len(files) == 1:
            path = Path(files[0])
            if self._stream_file(path, path.name):
                cleanup_job(job_id)
            return

        # Multiple files -> package the whole staging dir as one ZIP.
        base = job_dir(job_id)
        zip_path = STAGING_BASE / f"{job_id}.zip"
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
                for f in files:
                    zf.write(f, arcname=str(Path(f).relative_to(base)))
        except (OSError, ValueError) as exc:
            self._send_json(500, {"error": f"zip failed: {exc}"})
            return
        zip_name = f"{playlist_title or 'playlist'}.zip"
        if self._stream_file(zip_path, zip_name):
            cleanup_job(job_id)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/download":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            params = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"error": "invalid JSON body"})
            return

        url = (params.get("url") or "").strip()
        if not url:
            self._send_json(400, {"error": "missing url"})
            return

        job_id = uuid.uuid4().hex
        with JOBS_LOCK:
            JOBS[job_id] = {
                "id": job_id,
                "status": "queued",
                "stage": "queued",
                "url": url,
                "completed": 0,
                "current_title": None,
                "percent": "",
                "playlist_title": None,
                "files": [],
                "error": None,
            }
        threading.Thread(target=do_download, args=(job_id, params), daemon=True).start()
        self._send_json(200, {"job_id": job_id})


def main() -> int:
    STAGING_BASE.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"yt-dlp download server listening on http://{HOST}:{PORT}")
    print("Endpoints: GET /health, POST /download, GET /status?id=..., GET /file?id=...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
