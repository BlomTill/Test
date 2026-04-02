#!/usr/bin/env sh
set -e
cd "$(dirname "$0")"
echo "== News (news/) =="
python3 news/build_news.py
echo "== Video (video/) — pip install edge-tts; export OPENAI_API_KEY optional =="
mkdir -p video/output
python3 video/generate_ai_video.py --out video/output/social_vertical.mp4
echo "Done. Video: video/output/social_vertical.mp4"
