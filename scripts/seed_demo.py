#!/usr/bin/env python3
"""Fill an OpenClef instance with a small public-domain demo library.

Downloads eight engravings from the Mutopia Project (https://www.mutopiaproject.org),
each marked Public Domain on its Mutopia page, and uploads them with full
metadata through the normal API. Useful for trying OpenClef, screenshots, and
demos. Standard library only.

    OPENCLEF_PASSWORD=... python3 scripts/seed_demo.py \\
        --url http://localhost:8000 --username admin

Downloads are cached in --cache-dir (default ~/.cache/openclef-demo), so
re-runs don't fetch again. Re-running against the same instance uploads
duplicates; start from an empty library.
"""
from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

MUTOPIA = "https://www.mutopiaproject.org"

# Each entry was checked as "Public Domain" on its Mutopia piece page.
DEMO_LIBRARY = [
    {
        "file": f"{MUTOPIA}/ftp/DebussyC/L75/debussy_Ste_Bergamesq_Clair/debussy_Ste_Bergamesq_Clair-let.pdf",
        "source": f"{MUTOPIA}/cgibin/piece-info.cgi?id=1778",
        "metadata": {
            "title": "Clair de Lune",
            "subtitle": "Suite bergamasque, L. 75, No. 3",
            "composer": ["Debussy, Claude"],
            "instrumentation": ["Piano"],
            "key_signature": "Db major",
            "period": "Modern",
            "difficulty": 4,
        },
    },
    {
        "file": f"{MUTOPIA}/ftp/DebussyC/L66/debussy_Arabesque_1/debussy_Arabesque_1-let.pdf",
        "source": f"{MUTOPIA}/cgibin/piece-info.cgi?id=1777",
        "metadata": {
            "title": "Première Arabesque",
            "subtitle": "Deux arabesques, L. 66, No. 1",
            "composer": ["Debussy, Claude"],
            "instrumentation": ["Piano"],
            "key_signature": "E major",
            "period": "Modern",
            "difficulty": 3,
        },
    },
    {
        "file": f"{MUTOPIA}/ftp/ChopinFF/O10/chp-10-05/chp-10-05-let.pdf",
        "source": f"{MUTOPIA}/cgibin/piece-info.cgi?id=926",
        "metadata": {
            "title": "Étude Op. 10, No. 5 \"Black Key\"",
            "composer": ["Chopin, Frédéric"],
            "instrumentation": ["Piano"],
            "key_signature": "Gb major",
            "period": "Romantic",
            "difficulty": 5,
        },
    },
    {
        "file": f"{MUTOPIA}/ftp/ChopinFF/O10/op-10-12-wfi/op-10-12-wfi-let.pdf",
        "source": f"{MUTOPIA}/cgibin/piece-info.cgi?id=743",
        "metadata": {
            "title": "Étude Op. 10, No. 12 \"Revolutionary\"",
            "composer": ["Chopin, Frédéric"],
            "instrumentation": ["Piano"],
            "key_signature": "C minor",
            "period": "Romantic",
            "difficulty": 5,
        },
    },
    {
        "file": f"{MUTOPIA}/ftp/SchubertF/D328/Erlkoenig/Erlkoenig-let.pdf",
        "source": f"{MUTOPIA}/cgibin/piece-info.cgi?id=1030",
        "metadata": {
            "title": "Erlkönig",
            "subtitle": "D. 328",
            "composer": ["Schubert, Franz"],
            "lyricist": ["Goethe, Johann Wolfgang von"],
            "instrumentation": ["Voice", "Piano"],
            "key_signature": "G minor",
            "period": "Romantic",
            "language": ["German"],
            "difficulty": 4,
        },
    },
    {
        "file": f"{MUTOPIA}/ftp/SchubertF/D257/SchubertF-D257-Heidenroeslein/SchubertF-D257-Heidenroeslein-let.pdf",
        "source": f"{MUTOPIA}/cgibin/piece-info.cgi?id=1555",
        "metadata": {
            "title": "Heidenröslein",
            "subtitle": "D. 257",
            "composer": ["Schubert, Franz"],
            "lyricist": ["Goethe, Johann Wolfgang von"],
            "instrumentation": ["Voice", "Piano"],
            "key_signature": "G major",
            "period": "Romantic",
            "language": ["German"],
            "difficulty": 2,
        },
    },
    {
        "file": f"{MUTOPIA}/ftp/BachJS/BWV1009/cellosuite3/cellosuite3-let.pdf",
        "source": f"{MUTOPIA}/cgibin/piece-info.cgi?id=890",
        "metadata": {
            "title": "Cello Suite No. 3",
            "subtitle": "BWV 1009",
            "composer": ["Bach, Johann Sebastian"],
            "instrumentation": ["Cello"],
            "key_signature": "C major",
            "period": "Baroque",
            "difficulty": 4,
        },
        "part_type": "Other",
    },
    {
        "file": f"{MUTOPIA}/ftp/BachJS/BWV1017/bwv1017/bwv1017-let.pdf",
        "source": f"{MUTOPIA}/cgibin/piece-info.cgi?id=1733",
        "metadata": {
            "title": "Violin Sonata No. 4",
            "subtitle": "BWV 1017",
            "composer": ["Bach, Johann Sebastian"],
            "instrumentation": ["Violin", "Harpsichord"],
            "key_signature": "C minor",
            "period": "Baroque",
            "difficulty": 4,
        },
    },
]


def download(entry: dict, cache_dir: Path) -> bytes:
    path = cache_dir / entry["file"].rsplit("/", 1)[-1]
    if not path.exists():
        print(f"  downloading {path.name}")
        with urllib.request.urlopen(entry["file"], timeout=60) as response:
            path.write_bytes(response.read())
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        sys.exit(f"{path} is not a PDF; delete it and re-run")
    return data


def multipart(fields: dict[str, str], filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    chunks.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n".encode()
    )
    chunks += [data, f"\r\n--{boundary}--\r\n".encode()]
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://localhost:8000", help="OpenClef base URL")
    parser.add_argument("--username", required=True, help="account to upload as")
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache" / "openclef-demo")
    args = parser.parse_args()
    password = os.environ.get("OPENCLEF_PASSWORD") or getpass.getpass(f"Password for {args.username}: ")
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    login = urllib.request.Request(
        f"{args.url}/api/v1/auth/login",
        data=json.dumps({"username": args.username, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        opener.open(login, timeout=30)
    except urllib.error.HTTPError as exc:
        sys.exit(f"sign-in failed: HTTP {exc.code}")

    for entry in DEMO_LIBRARY:
        title = entry["metadata"]["title"]
        data = download(entry, args.cache_dir)
        fields = {"metadata": json.dumps(entry["metadata"]), "part_type": entry.get("part_type", "Full Score")}
        body, content_type = multipart(fields, entry["file"].rsplit("/", 1)[-1], data)
        request = urllib.request.Request(
            f"{args.url}/api/v1/arrangements/upload", data=body, headers={"Content-Type": content_type}
        )
        try:
            with opener.open(request, timeout=120) as response:
                pages = json.load(response)["part"]["page_count"]
            print(f"  added {title} ({pages} pages)")
        except urllib.error.HTTPError as exc:
            sys.exit(f"upload of {title} failed: HTTP {exc.code} {exc.read()[:200]!r}")
    print(f"Done: {len(DEMO_LIBRARY)} pieces. Scores: Mutopia Project, public domain.")


if __name__ == "__main__":
    main()
