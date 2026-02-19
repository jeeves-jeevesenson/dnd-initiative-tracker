#!/usr/bin/env python3
"""
aidedd_image_archive.py

Download monster images from AideDD by monster slug, saving locally as <slug>.<ext>.
Also supports batch download from monster-list.xml (list of <monster>slug</monster> nodes).

Examples:
  # single
  python aidedd_image_archive.py --slug ape --outdir Monsters/Images

  # batch from XML (your uploaded file path)
  python aidedd_image_archive.py --xml /mnt/data/monster-list.xml --outdir Monsters/Images --sleep 0.2

  # batch but limit for testing
  python aidedd_image_archive.py --xml /mnt/data/monster-list.xml --outdir Monsters/Images --limit 20 --sleep 0.2
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Optional, Tuple, List


AIDEDD_BASE = "https://www.aidedd.org"
AIDEDD_MONSTER_BASE = f"{AIDEDD_BASE}/monster/"


def safe_slug(slug: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", (slug or "").strip().lower()).strip("-")
    return s


def monster_page_url(slug: str) -> str:
    return f"{AIDEDD_MONSTER_BASE}{safe_slug(slug)}"


def request_headers(referer: Optional[str] = None) -> dict:
    h = {
        "User-Agent": "dnd-init-tracker/image-archiver/1.0",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }
    if referer:
        h["Referer"] = referer
    return h


def fetch_text(url: str, timeout: float = 15.0) -> str:
    req = urllib.request.Request(url, headers=request_headers())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        # AideDD pages are UTF-8; be tolerant.
        return data.decode("utf-8", errors="replace")


def extract_aidedd_image_src(raw_html: str) -> Optional[str]:
    """
    Returns the raw src/content value, possibly relative like 'img/ape.jpg'.
    Priority:
      1) og:image meta
      2) <div class='picture'> ... <img src='...'>
      3) any <img src> starting with img/ or containing /monster/img/
    """
    if not raw_html:
        return None

    # 1) og:image
    for pattern in (
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    ):
        m = re.search(pattern, raw_html, flags=re.IGNORECASE)
        if m:
            return m.group(1)

    # Common AideDD structure: <div class='picture'><img src='img/ape.jpg' ...></div>
    picture_div_pattern = re.compile(
        r"<div[^>]+class=[\"'][^\"']*\bpicture\b[^\"']*[\"'][^>]*>(.*?)</div>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    img_src_pattern = re.compile(
        r"<img[^>]+src=[\"']([^\"']+)[\"'][^>]*>",
        flags=re.IGNORECASE,
    )

    for div_m in picture_div_pattern.finditer(raw_html):
        block = div_m.group(1)
        img_m = img_src_pattern.search(block)
        if img_m:
            src = (img_m.group(1) or "").strip()
            if src:
                return src

    # 3) fallback: any <img> with likely paths
    for img_m in img_src_pattern.finditer(raw_html):
        src = (img_m.group(1) or "").strip()
        if not src:
            continue
        lowered = src.lower()
        if lowered.startswith("img/") or "/monster/img/" in lowered:
            return src

    return None


def normalize_aidedd_url(src: str, page_url: str) -> Optional[str]:
    candidate = html.unescape((src or "").strip())
    if not candidate:
        return None

    absolute = urllib.parse.urljoin(page_url, candidate)
    parsed = urllib.parse.urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return None
    if "aidedd.org" not in (parsed.netloc or ""):
        return None

    # Force https
    if absolute.startswith("http://"):
        absolute = "https://" + absolute[len("http://") :]
    return absolute


def guess_extension(image_url: str, content_type: Optional[str]) -> str:
    # Prefer URL path extension
    path = urllib.parse.urlparse(image_url).path
    _, ext = os.path.splitext(path)
    ext = (ext or "").lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ".jpg" if ext == ".jpeg" else ext

    # Fallback on content-type
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        mapping = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }
        if ct in mapping:
            return mapping[ct]

    # default
    return ".jpg"


def fetch_image_bytes(image_url: str, referer_page: str, timeout: float = 20.0) -> Tuple[bytes, Optional[str]]:
    req = urllib.request.Request(image_url, headers=request_headers(referer=referer_page))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        ctype = resp.headers.get("Content-Type")
        return data, ctype


def download_one(slug: str, outdir: str, overwrite: bool, manifest_fp) -> bool:
    s = safe_slug(slug)
    if not s:
        return False

    page = monster_page_url(s)
    try:
        raw = fetch_text(page)
    except Exception as e:
        manifest_fp.write(json.dumps({"slug": s, "status": "page_fetch_error", "error": str(e), "page": page}) + "\n")
        return False

    src = extract_aidedd_image_src(raw)
    if not src:
        manifest_fp.write(json.dumps({"slug": s, "status": "no_image_found", "page": page}) + "\n")
        return False

    image_url = normalize_aidedd_url(src, page)
    if not image_url:
        manifest_fp.write(json.dumps({"slug": s, "status": "bad_image_url", "src": src, "page": page}) + "\n")
        return False

    # If already exists (any ext), skip unless overwrite
    os.makedirs(outdir, exist_ok=True)
    existing = [fn for fn in os.listdir(outdir) if fn == s + ".jpg" or fn == s + ".png" or fn == s + ".webp" or fn == s + ".gif"]
    if existing and not overwrite:
        manifest_fp.write(json.dumps({"slug": s, "status": "skipped_exists", "file": os.path.join(outdir, existing[0]), "image_url": image_url}) + "\n")
        return True

    try:
        data, ctype = fetch_image_bytes(image_url, referer_page=page)
    except Exception as e:
        manifest_fp.write(json.dumps({"slug": s, "status": "image_fetch_error", "error": str(e), "image_url": image_url, "page": page}) + "\n")
        return False

    ext = guess_extension(image_url, ctype)
    outpath = os.path.join(outdir, s + ext)

    if not overwrite:
        # If we're switching ext, avoid clobbering an existing different ext
        if os.path.exists(outpath):
            manifest_fp.write(json.dumps({"slug": s, "status": "skipped_exists", "file": outpath, "image_url": image_url}) + "\n")
            return True

    # Write file
    with open(outpath, "wb") as f:
        f.write(data)

    manifest_fp.write(json.dumps({
        "slug": s,
        "status": "ok",
        "file": outpath,
        "image_url": image_url,
        "content_type": ctype,
        "bytes": len(data),
    }) + "\n")
    return True


def slugs_from_xml(xml_path: str) -> List[str]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    slugs = []
    for node in root.findall("monster"):
        if node.text and node.text.strip():
            slugs.append(node.text.strip())
    return slugs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", help="Single monster slug to fetch (e.g., ape)")
    ap.add_argument("--xml", help="Path to monster-list.xml (contains <monster>slug</monster> entries)")
    ap.add_argument("--outdir", default="Monsters/Images", help="Output directory")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of slugs processed (0 = no limit)")
    ap.add_argument("--sleep", type=float, default=0.2, help="Sleep seconds between downloads in batch")
    ap.add_argument("--manifest", default="manifest.jsonl", help="Manifest output (json lines)")
    args = ap.parse_args()

    if not args.slug and not args.xml:
        ap.error("Provide either --slug or --xml")

    with open(args.manifest, "a", encoding="utf-8") as mf:
        if args.slug:
            ok = download_one(args.slug, args.outdir, args.overwrite, mf)
            raise SystemExit(0 if ok else 2)

        slugs = slugs_from_xml(args.xml)
        if args.limit and args.limit > 0:
            slugs = slugs[: args.limit]

        ok_count = 0
        fail_count = 0
        for i, slug in enumerate(slugs, start=1):
            ok = download_one(slug, args.outdir, args.overwrite, mf)
            if ok:
                ok_count += 1
            else:
                fail_count += 1
            if args.sleep and i < len(slugs):
                time.sleep(args.sleep)

        print(f"Done. ok={ok_count} fail={fail_count} outdir={args.outdir} manifest={args.manifest}")
        raise SystemExit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
