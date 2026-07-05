# music-downloader

A simple YouTube/YouTube Music playlist downloader that saves audio into per-artist (channel) folders.

## Requirements

- Python 3.10+
- `yt-dlp` (installed from `requirements.txt`)
- `ffmpeg` available in `PATH`
- JavaScript runtime: `deno` (preferred) or `node`

## Installation (Windows)

1. Install system tools:

```powershell
winget install Gyan.FFmpeg
winget install DenoLand.Deno
```

If Node.js is not installed, add it:

```powershell
winget install OpenJS.NodeJS
```

2. Install Python dependency:

```powershell
python -m pip install -r requirements.txt
```

## Configuration

You can use `config.json` and/or CLI parameters.

Default config path is `./config.json` (project root).

Priority order is: CLI arguments > config file values > built-in defaults.

## Usage

Check requirements:

```powershell
python main.py --check-requirements
```

Run using config (`url` must be present in `config.json`):

```powershell
python main.py
```

## CLI Parameters

- `url` (positional, optional): YouTube/YouTube Music playlist URL. If set, it overrides `url` in config.
- `-o, --output`: Output root directory. Artist/channel subfolders are created inside it.
- `-f, --format`: Target audio format. Choices: `mp3`, `m4a`, `opus`, `flac`, `wav`.
- `-q, --quality`: Bitrate in kbps for lossy codecs (`mp3`, `m4a`, `opus`). Ignored for `flac`/`wav`.
- `-l, --limit`: Download only the first N tracks from the playlist.
- `-c, --config`: Path to a custom JSON config file.
- `-n, --dry-run`: Simulate download without writing files.
- `--verbose`: Enable verbose `yt-dlp` logs.
- `--check-requirements`: Verify `ffmpeg`, JS runtime (`deno`/`node`), and `yt-dlp`, then exit.

