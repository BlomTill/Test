#!/usr/bin/env python3
"""
Stitch images into a single MP4 with ffmpeg (slideshow). Use for frames exported
from an AI video tool, or storyboard stills you own the rights to.

Social upload automation:
  • YouTube: Official Data API supports uploads with OAuth; see Google’s docs.
    This repo does not ship OAuth secrets — configure credentials locally if you
    add an uploader script.
  • TikTok / Instagram Reels: Posting APIs are restricted (business verification,
    product programs). Unofficial “bots” often violate Terms of Service and can
    ban accounts — avoid them for production.

Requires: ffmpeg on PATH.
Example:
  python3 video/ai_video_export.py --images-dir ./frames --out ./out/preview.mp4
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="Create MP4 slideshow from images.")
    p.add_argument("--images-dir", required=True, type=Path, help="Folder of images (sorted by name).")
    p.add_argument("--out", required=True, type=Path, help="Output .mp4 path.")
    p.add_argument("--seconds", type=float, default=3.0, help="Seconds per image.")
    p.add_argument("--size", default="1080:1920", help="ffmpeg scale WxH or w:h, default vertical 9:16.")
    args = p.parse_args()

    if not shutil.which("ffmpeg"):
        print("ffmpeg not found. Install ffmpeg (e.g. brew install ffmpeg).", file=sys.stderr)
        return 1

    img_dir: Path = args.images_dir
    if not img_dir.is_dir():
        print(f"Not a directory: {img_dir}", file=sys.stderr)
        return 1

    exts = {".png", ".jpg", ".jpeg", ".webp"}
    images = sorted(
        f for f in img_dir.iterdir() if f.is_file() and f.suffix.lower() in exts
    )
    if not images:
        print(f"No images ({', '.join(sorted(exts))}) in {img_dir}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    w, h = args.size.split(":", 1)

    with tempfile.TemporaryDirectory() as tmp:
        list_path = Path(tmp) / "files.txt"
        lines = []
        for img in images:
            safe = img.resolve()
            lines.append(f"file '{safe}'")
            lines.append(f"duration {args.seconds}")
        lines.append(f"file '{images[-1].resolve()}'")
        list_path.write_text("\n".join(lines), encoding="utf-8")

        vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-vf",
            vf,
            "-r",
            "30",
            "-movflags",
            "+faststart",
            str(args.out),
        ]
        subprocess.run(cmd, check=True)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
