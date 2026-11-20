from __future__ import annotations

import argparse
import json
import sys
import shutil
import subprocess
from pathlib import Path

import yt_dlp


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: could not read config at {path}: {exc}", file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        print(f"Warning: config at {path} must be a JSON object; ignoring.", file=sys.stderr)
        return {}
    return data


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="music-downloader",description="Download a YouTube playlist as high-quality audio, organized per-artist.",formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("url", nargs="?", default=None, help="YouTube or YouTube Music playlist URL. Omit when using --check-requirements.")
    p.add_argument("-o", "--output", default=None, help="Output root directory. Per-artist subfolders are created inside.")
    p.add_argument("-f", "--format", default=None, choices=["mp3", "m4a", "opus", "flac", "wav"], help="Target audio codec. Requires ffmpeg in PATH.")
    p.add_argument("-q", "--quality", default=None, help="Bitrate in kbps for lossy codecs (mp3/opus/m4a). Ignored for flac/wav.")
    p.add_argument("-l", "--limit", type=int, default=None, help="Download at most N tracks from the beginning of the playlist.")
    p.add_argument("-c", "--config", default=None, help=f"Path to JSON config file. Default: {DEFAULT_CONFIG_PATH}")
    p.add_argument("-n", "--dry-run", action="store_true", help="Show what would be downloaded without saving any files.")
    p.add_argument("--verbose", action="store_true", help="Enable yt-dlp verbose output for debugging.")
    p.add_argument("--remote-components", default=None, help="yt-dlp remote components to solve YouTube JS challenges (fixes 403 errors). E.g. 'ejs:github' (recommended) or 'ejs:npm'. Comma-separate multiple; use 'none' to disable. Default: ejs:github")
    p.add_argument("--player-client", default=None, help="YouTube player client(s) used for extraction (fixes media 403 on some networks). Comma-separate to try in order; use 'none' for yt-dlp default. Default: web_embedded")
    p.add_argument("--check-requirements", action="store_true", help="Verify that ffmpeg and a JS runtime (deno/node) are installed, then exit.")

    return p.parse_args(argv)


def resolve_effective(args: argparse.Namespace, file_cfg: dict) -> dict:
    def pick(key: str, default):
        cli_val = getattr(args, key, None)
        if cli_val is not None:
            return cli_val
        return file_cfg.get(key, default)

    return {
        "url": pick("url", None),
        "output_dir": str(Path(pick("output", "~/music")).expanduser()),
        "format": pick("format", "mp3"),
        "quality": str(pick("quality", 320)),
        "limit": pick("limit", None),
        "remote_components": pick("remote_components", "ejs:github"),
        "player_client": pick("player_client", "web_embedded"),
    }


def build_ydl_opts(cfg: dict, dry_run: bool, verbose: bool) -> dict:
    output_dir = cfg["output_dir"]

    outtmpl = str(
        Path(output_dir) / "%(channel,uploader,creator)s" / "%(title)s.%(ext)s"
    )

    opts: dict = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "restrictfilenames": False,
        "ignoreerrors": True,
        "writethumbnail": False,
        "noplaylist": False,
        "quiet": not verbose,
        "verbose": verbose,
        "js_runtimes": {"deno": {}, "node": {}},
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": cfg["format"],
                "preferredquality": cfg["quality"],
            },
            {"key": "FFmpegMetadata"},
        ],
    }

    raw_components = cfg["remote_components"]
    if isinstance(raw_components, str):
        raw_components = raw_components.split(",")
    if raw_components:
        components = {
            str(c).strip()
            for c in raw_components
            if str(c).strip() and str(c).strip().lower() != "none"
        }
        if components:
            opts["remote_components"] = components

    raw_clients = cfg["player_client"]
    if isinstance(raw_clients, str):
        raw_clients = raw_clients.split(",")
    if raw_clients:
        clients = [
            str(c).strip()
            for c in raw_clients
            if str(c).strip() and str(c).strip().lower() != "none"
        ]
        if clients:
            opts["extractor_args"] = {"youtube": {"player_client": clients}}

    if cfg["limit"]:
        opts["playlist_items"] = f"1-{int(cfg['limit'])}"

    if dry_run:
        opts["simulate"] = True
        opts["skip_download"] = True

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    return opts


def run(url: str, cfg: dict, dry_run: bool, verbose: bool) -> int:
    if not dry_run:
        print(f"Output root: {cfg['output_dir']}")
        print(f"Format:      {cfg['format']} @ {cfg['quality']} kbps")
        if cfg["limit"]:
            print(f"Limit:       {cfg['limit']} tracks")
        print(f"URL:         {url}")
        print()

    ydl_opts = build_ydl_opts(cfg, dry_run, verbose)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ret = ydl.download([url])
            return 0 if ret == 0 else 1
    except yt_dlp.utils.DownloadError as exc:
        print(f"yt-dlp error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.check_requirements:
        return check_requirements()

    cfg_path = Path(args.config).expanduser() if args.config else DEFAULT_CONFIG_PATH
    file_cfg = load_config(cfg_path)
    cfg = resolve_effective(args, file_cfg)

    if not cfg["url"]:
        print("error: playlist URL is required (pass as ARG or set 'url' in config)",file=sys.stderr)
        return 2

    return run(cfg["url"], cfg, args.dry_run, args.verbose)


def check_requirements() -> int:
    failures = 0

    def check(label: str, cmd: str, version_args: list[str]) -> bool:
        path = shutil.which(cmd)
        if not path:
            print(f"[FAIL] {label}: '{cmd}' not found on PATH", file=sys.stderr)
            return False
        try:
            out = subprocess.run([cmd, *version_args], capture_output=True, text=True, timeout=10)
            first = (out.stdout or out.stderr).strip().splitlines()[0]
            print(f"[OK]   {label}: {first}")
            return True
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"[FAIL] {label}: {exc}", file=sys.stderr)
            return False

    print("Checking local requirements for music-downloader...")
    print()

    if not check("ffmpeg", "ffmpeg", ["-version"]):
        failures += 1
    if not check("deno (JS runtime, preferred)", "deno", ["--version"]):
        failures += 1
        check("node (JS runtime, fallback)", "node", ["--version"])
    if not check("yt-dlp", "yt-dlp", ["--version"]):
        failures += 1

    print()
    if failures:
        print(f"{failures} check(s) failed.", file=sys.stderr)
        return 1
    print("All requirements satisfied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
