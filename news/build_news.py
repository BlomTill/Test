#!/usr/bin/env python3
"""
Fetch configured RSS/Atom feeds, optionally tag retailer URLs with affiliate params,
and write docs/news.html. Uses only the Python standard library.

Config: news/news_config.json · Template: news/templates/news_page.html

Compliance: You must follow each affiliate program’s rules (Amazon Associates,
etc.), FTC/EU disclosure rules, and Google’s spam policies. Fully automated
thin affiliate pages can violate program terms or get de-indexed — use feeds
you have rights to aggregate, add real value, and review output regularly.
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "news" / "news_config.json"
TEMPLATE_PATH = ROOT / "news" / "templates" / "news_page.html"
OUT_PATH = ROOT / "docs" / "news.html"
TRENDING_PATH = ROOT / "docs" / "trending.json"

ATOM_NS = "http://www.w3.org/2005/Atom"
ATOM = f"{{{ATOM_NS}}}"

TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(text: str) -> str:
    return TAG_RE.sub("", text or "")


def elem_text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return "".join(el.itertext()).strip()


def parse_ts_rss(s: str) -> float:
    if not s:
        return 0.0
    try:
        dt = parsedate_to_datetime(s.strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0.0


def parse_ts_atom(s: str) -> float:
    if not s:
        return 0.0
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0.0


def fetch_feed_xml(url: str, timeout: int = 35) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "PassiveNewsBuilder/1.0 (+https://example.local)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def parse_rss_channel(root: ET.Element) -> list[dict]:
    out: list[dict] = []
    channel = root.find("channel")
    if channel is None:
        return out
    for item in channel.findall("item"):
        title = elem_text(item.find("title")) or "Untitled"
        link_el = item.find("link")
        link = (link_el.text or "").strip() if link_el is not None else ""
        desc = item.find("description")
        summary = elem_text(desc) if desc is not None else ""
        pub = item.find("pubDate")
        pub_raw = pub.text.strip() if pub is not None and pub.text else ""
        when = parse_ts_rss(pub_raw)
        if not link:
            guid = item.find("guid")
            if guid is not None and guid.text and guid.text.startswith("http"):
                link = guid.text.strip()
        out.append(
            {
                "title": title.strip(),
                "link": link,
                "summary": summary,
                "when": when,
            }
        )
    return out


def parse_atom_feed(root: ET.Element) -> list[dict]:
    out: list[dict] = []
    for entry in root.findall(f"{ATOM}entry"):
        title = elem_text(entry.find(f"{ATOM}title")) or "Untitled"
        link = ""
        for le in entry.findall(f"{ATOM}link"):
            if le.get("rel") in (None, "alternate"):
                link = le.get("href") or ""
                break
        if not link:
            le = entry.find(f"{ATOM}link")
            if le is not None:
                link = le.get("href") or ""
        summ_el = entry.find(f"{ATOM}summary")
        content_el = entry.find(f"{ATOM}content")
        if content_el is not None:
            summary = elem_text(content_el)
        elif summ_el is not None:
            summary = elem_text(summ_el)
        else:
            summary = ""
        updated = entry.find(f"{ATOM}updated")
        published = entry.find(f"{ATOM}published")
        raw = ""
        if published is not None and published.text:
            raw = published.text.strip()
        elif updated is not None and updated.text:
            raw = updated.text.strip()
        when = parse_ts_atom(raw)
        out.append(
            {
                "title": title.strip(),
                "link": link.strip(),
                "summary": summary,
                "when": when,
            }
        )
    return out


def parse_feed_entries(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    if root.tag == f"{ATOM}feed":
        return parse_atom_feed(root)
    if root.find("channel") is not None:
        return parse_rss_channel(root)
    return []


def host_matches(host: str, hosts: list[str]) -> bool:
    host = host.lower()
    for raw in hosts:
        h = raw.lower().lstrip(".")
        if host == h or host.endswith("." + h):
            return True
    return False


def apply_affiliate_rules(url: str, rules: list[dict]) -> tuple[str, bool]:
    if not url or not rules:
        return url, False
    try:
        parts = urlparse(url)
    except ValueError:
        return url, False
    host = (parts.netloc or "").lower()
    for rule in rules:
        hosts = rule.get("hosts") or []
        if not hosts or not host_matches(host, hosts):
            continue
        param = rule.get("param")
        val = rule.get("value")
        if not param or val is None or "REPLACE-WITH" in str(val):
            continue
        q = parse_qs(parts.query, keep_blank_values=True)
        q[param] = [str(val)]
        new_query = urlencode(q, doseq=True)
        new_parts = parts._replace(query=new_query)
        return urlunparse(new_parts), True
    return url, False


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_first_headline_from_config() -> Optional[str]:
    """Newest headline from the first working feed in ``news/news_config.json`` (for video topics)."""
    try:
        cfg = load_config()
    except OSError:
        return None
    for feed_cfg in cfg.get("feeds", []):
        url = feed_cfg.get("url")
        if not url:
            continue
        try:
            xml_bytes = fetch_feed_xml(url)
            raw = parse_feed_entries(xml_bytes)
            if not raw:
                continue
            raw.sort(key=lambda x: float(x.get("when") or 0), reverse=True)
            t = (raw[0].get("title") or "").strip()
            if t:
                return t
        except Exception:
            continue
    return None


def render_items(entries: list[dict]) -> str:
    blocks = []
    for e in entries:
        title = html.escape(e["title"])
        link = html.escape(e["link"], quote=True)
        src = html.escape(e["source"])
        summ = html.escape(e["summary"]) if e["summary"] else ""
        aff = (
            ' rel="noopener noreferrer sponsored"'
            if e.get("affiliate")
            else ' rel="noopener noreferrer"'
        )
        sum_html = f'<p class="news-summary">{summ}</p>' if summ else ""
        blocks.append(
            f"""<li class="news-item">
  <a href="{link}"{aff} target="_blank" class="news-title">{title}</a>
  <p class="news-meta"><span class="news-source">{src}</span></p>
  {sum_html}
</li>"""
        )
    return "\n".join(blocks)


def main() -> None:
    cfg = load_config()
    per_feed = int(cfg.get("max_items_per_feed", 10))
    max_total = int(cfg.get("max_total_items", 40))
    aff_rules = cfg.get("affiliate_query_rules") or []
    strip_html = bool(cfg.get("strip_html_from_summary", True))
    max_chars = int(cfg.get("summary_max_chars", 220))

    collected: list[dict] = []
    for feed_cfg in cfg.get("feeds", []):
        url = feed_cfg.get("url")
        name = feed_cfg.get("name") or url
        if not url:
            continue
        try:
            xml_bytes = fetch_feed_xml(url)
            raw_entries = parse_feed_entries(xml_bytes)
        except (urllib.error.URLError, urllib.error.HTTPError, ET.ParseError, TimeoutError) as ex:
            print(f"Skip feed {name!r}: {ex}")
            continue
        count = 0
        for ent in raw_entries:
            if count >= per_feed:
                break
            title = ent.get("title") or "Untitled"
            link = (ent.get("link") or "").strip()
            if not link:
                continue
            new_link, is_aff = apply_affiliate_rules(link, aff_rules)
            summary = ent.get("summary") or ""
            if strip_html:
                summary = strip_tags(summary)
            summary = " ".join(summary.split())
            if len(summary) > max_chars:
                summary = summary[: max_chars - 1].rsplit(" ", 1)[0] + "…"
            collected.append(
                {
                    "title": title,
                    "link": new_link,
                    "source": name,
                    "summary": summary,
                    "affiliate": is_aff,
                    "when": float(ent.get("when") or 0),
                }
            )
            count += 1

    collected.sort(key=lambda x: x["when"], reverse=True)
    collected = collected[:max_total]

    disclosure = (
        "This page may contain affiliate links. If you buy through them, the site may earn a "
        "commission at no extra cost to you. Editorial selections are automated from RSS; "
        "verify details on the retailer before purchasing."
    )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    items_html = render_items(collected)
    out = template.replace("%%PAGE_TITLE%%", html.escape(cfg.get("page_title", "News")))
    out = out.replace("%%PAGE_HEADING%%", html.escape(cfg.get("page_heading", "News")))
    out = out.replace("%%INTRO%%", html.escape(cfg.get("intro", "")))
    out = out.replace("%%GENERATED_AT%%", generated)
    out = out.replace("%%DISCLOSURE%%", disclosure)
    out = out.replace("%%ITEMS%%", items_html)

    OUT_PATH.write_text(out, encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({len(collected)} items)")

    max_trending = int(cfg.get("max_trending_items", 8))
    trending = [
        {
            "title": e["title"],
            "url": e["link"],
            "source": e["source"],
            "affiliate": e["affiliate"],
        }
        for e in collected[:max_trending]
        if e["link"]
    ]
    trending_payload = {"updated": generated, "items": trending}
    TRENDING_PATH.write_text(
        json.dumps(trending_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {TRENDING_PATH} ({len(trending)} trending items)")


if __name__ == "__main__":
    main()
