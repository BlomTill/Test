#!/usr/bin/env python3
"""
Build a vertical (9:16) MP4 for social: AI image prompts → Pollinations images,
optional OpenAI JSON script, optional Microsoft Edge TTS (edge-tts), ffmpeg mux.

Requires: ffmpeg (+ ffprobe) on PATH.

Config: video/video_ai_config.json

Optional:
  pip install edge-tts
  export OPENAI_API_KEY=...   → richer slide scripts + image prompts

Topic resolution order: --topic, env VIDEO_TOPIC, newest RSS headline from
news/news_config.json, then default_topic in video_ai_config.json.

Upload: platforms differ; this script only writes a file. Use YouTube Data API
or manual upload for TikTok/Reels. See video/ai_video_export.py docstring.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
VIDEO_DIR = Path(__file__).resolve().parent
VIDEO_CFG = VIDEO_DIR / "video_ai_config.json"

sys.path.insert(0, str(ROOT / "news"))
import build_news as bn  # noqa: E402


def load_video_cfg() -> dict:
    if VIDEO_CFG.is_file():
        with open(VIDEO_CFG, encoding="utf-8") as f:
            return json.load(f)
    return {}


def fallback_slides(topic: str, n: int) -> list[dict]:
    topic = (topic or "tech news").strip()
    seeds = [
        (
            "cinematic abstract technology background, vertical composition, soft neon, photorealistic, 8k, no text",
            "Here's what caught our attention today.",
        ),
        (
            "sleek gadgets and devices on minimal desk, studio lighting, vertical frame, no text",
            "The details matter more than the headline.",
        ),
        (
            "futuristic city skyline data visualization, depth of field, vertical, no text",
            "Stay curious — the story keeps evolving.",
        ),
        (
            "macro circuit board with subtle glow, shallow depth of field, vertical, no text",
            "Worth a look before you buy anything.",
        ),
        (
            "calm gradient waves abstract art, modern, vertical, no text",
            "Thanks for watching — links in the description.",
        ),
    ]
    out: list[dict] = []
    for i in range(n):
        img, line = seeds[i % len(seeds)]
        out.append(
            {
                "image_prompt": f"{img} Theme context: {topic[:120]}",
                "line": line if i else f"Today in tech: {topic[:80]}",
            }
        )
    return out


def openai_slides(topic: str, n: int, model: str, api_key: str) -> list[dict]:
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You write JSON only. Slides for a short vertical faceless social video.",
                },
                {
                    "role": "user",
                    "content": (
                        f'Topic: "{topic}"\n'
                        f"Create exactly {n} slides. Each slide must have:\n"
                        '- "image_prompt": English visual description for AI image generation, '
                        "vertical 9:16 friendly, no words or logos in the image.\n"
                        '- "line": one narration sentence, max 16 words, conversational.\n'
                        'Return JSON: {"slides":[{"image_prompt":"...","line":"..."}]}'
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.75,
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    text = data["choices"][0]["message"]["content"]
    parsed = json.loads(text)
    slides = parsed.get("slides") or []
    cleaned = []
    for s in slides[:n]:
        ip = (s.get("image_prompt") or "").strip()
        line = (s.get("line") or "").strip()
        if ip and line:
            cleaned.append({"image_prompt": ip, "line": line})
    if len(cleaned) < n:
        cleaned = fallback_slides(topic, n)
    return cleaned[:n]


def download_pollinations(
    prompt: str, out_path: Path, width: int, height: int, nologo: bool
) -> None:
    q = quote(prompt[:900], safe="")
    extra = f"width={width}&height={height}"
    if nologo:
        extra += "&nologo=true"
    url = f"https://image.pollinations.ai/prompt/{q}?{extra}"
    req = urllib.request.Request(url, headers={"User-Agent": "PassiveVideoGen/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    if len(data) < 2000:
        raise RuntimeError("Image response too small (likely error page).")
    if data[:2] != b"\xff\xd8" and data[:4] != b"\x89PNG":
        raise RuntimeError("Downloaded file does not look like JPEG/PNG.")
    out_path.write_bytes(data)


async def edge_tts_save(text: str, out_mp3: Path, voice: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_mp3))


def run_edge_tts(text: str, out_mp3: Path, voice: str) -> None:
    asyncio.run(edge_tts_save(text, out_mp3, voice))


def ffprobe_duration(path: Path) -> float:
    cmd = [
        shutil.which("ffprobe") or "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return float(out)


def build_slideshow_mp4(
    images: list[Path],
    seconds_each: float,
    out_mp4: Path,
    w: int,
    h: int,
) -> None:
    import tempfile

    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    with tempfile.TemporaryDirectory() as tmp:
        list_path = Path(tmp) / "files.txt"
        lines = []
        for img in images:
            lines.append(f"file '{img.resolve()}'")
            lines.append(f"duration {seconds_each}")
        lines.append(f"file '{images[-1].resolve()}'")
        list_path.write_text("\n".join(lines), encoding="utf-8")
        vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
        cmd = [
            ffmpeg,
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
            "-an",
            str(out_mp4),
        ]
        subprocess.run(cmd, check=True)


def mux_audio(video: Path, audio: Path, out: Path) -> None:
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(out),
    ]
    subprocess.run(cmd, check=True)


def resolve_topic(args: argparse.Namespace, vcfg: dict) -> str:
    if args.topic:
        return args.topic.strip()
    env = os.environ.get("VIDEO_TOPIC", "").strip()
    if env:
        return env
    h = bn.get_first_headline_from_config()
    if h:
        return h
    return str(vcfg.get("default_topic") or "Technology news")


def main() -> int:
    p = argparse.ArgumentParser(description="Generate AI-assisted social video (images + voice + ffmpeg).")
    p.add_argument("--topic", default="", help="Override video topic / script seed.")
    p.add_argument(
        "--out",
        type=Path,
        default=VIDEO_DIR / "output" / "social_vertical.mp4",
        help="Output MP4 path.",
    )
    p.add_argument("--no-openai", action="store_true", help="Skip OpenAI even if OPENAI_API_KEY is set.")
    p.add_argument("--no-tts", action="store_true", help="No narration audio; fixed timing only.")
    p.add_argument("--slides", type=int, default=0, help="Override slide count.")
    args = p.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("Install ffmpeg and ffprobe (e.g. brew install ffmpeg).", file=sys.stderr)
        return 1

    vcfg = load_video_cfg()
    n = args.slides or int(vcfg.get("slide_count") or 5)
    n = max(2, min(n, 12))
    w = int(vcfg.get("vertical_width") or 1080)
    h = int(vcfg.get("vertical_height") or 1920)
    voice = str(vcfg.get("voice") or "en-US-AriaNeural")
    delay = float(vcfg.get("pollinations_delay_seconds") or 1.0)
    nologo = bool(vcfg.get("pollinations_nologo", True))
    fallback_sec = float(vcfg.get("seconds_per_slide_fallback") or 3.5)
    model = str(vcfg.get("openai_model") or "gpt-4o-mini")

    topic = resolve_topic(args, vcfg)
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if api_key and not args.no_openai:
        try:
            slides = openai_slides(topic, n, model, api_key)
            print("Used OpenAI for slide script.")
        except Exception as ex:
            print(f"OpenAI failed ({ex}); using template slides.", file=sys.stderr)
            slides = fallback_slides(topic, n)
    else:
        slides = fallback_slides(topic, n)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    work = args.out.parent / f".work_{random.randint(1000, 9999)}"
    work.mkdir(parents=True, exist_ok=True)
    images: list[Path] = []
    try:
        for i, s in enumerate(slides):
            pth = work / f"slide_{i:02d}.jpg"
            for attempt in range(3):
                try:
                    download_pollinations(s["image_prompt"], pth, w, h, nologo)
                    images.append(pth)
                    break
                except Exception as ex:
                    print(f"Image {i} attempt {attempt + 1}: {ex}", file=sys.stderr)
                    time.sleep(2 + attempt)
            else:
                print(f"Failed slide {i}; aborting.", file=sys.stderr)
                return 1
            time.sleep(delay + random.uniform(0, 0.3))

        narration = " ".join(s["line"] for s in slides)
        silent_vid = work / "silent.mp4"

        if args.no_tts:
            build_slideshow_mp4(images, fallback_sec, silent_vid, w, h)
            shutil.copyfile(silent_vid, args.out)
        else:
            try:
                import edge_tts  # noqa: F401
            except ImportError:
                print("Install edge-tts: pip install edge-tts", file=sys.stderr)
                build_slideshow_mp4(images, fallback_sec, silent_vid, w, h)
                shutil.copyfile(silent_vid, args.out)
            else:
                try:
                    mp3 = work / "voice.mp3"
                    run_edge_tts(narration, mp3, voice)
                    dur = ffprobe_duration(mp3)
                    sec_each = max(0.8, dur / len(images))
                    build_slideshow_mp4(images, sec_each, silent_vid, w, h)
                    if ffprobe_duration(silent_vid) < dur - 0.25:
                        sec_each = max(0.85, (dur + 0.5) / len(images))
                        build_slideshow_mp4(images, sec_each, silent_vid, w, h)
                    mux_audio(silent_vid, mp3, args.out)
                except Exception as ex:
                    print(f"TTS/mux failed ({ex}); writing silent video.", file=sys.stderr)
                    build_slideshow_mp4(images, fallback_sec, silent_vid, w, h)
                    shutil.copyfile(silent_vid, args.out)

        print(f"Wrote {args.out.resolve()}")
        print(f"Topic: {topic[:120]}")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
