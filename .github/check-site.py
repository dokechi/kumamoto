#!/usr/bin/env python3
"""Static checks for the three public pages, plus optional remote checks."""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
FILES = ("index.html", "resident.html", "genba.html")
BASE_URL = "https://dokechi.github.io/kumamoto/"
EXPECTED_URLS = {
    "index.html": BASE_URL,
    "resident.html": f"{BASE_URL}resident.html",
    "genba.html": f"{BASE_URL}genba.html",
}
USER_AGENT = "Mozilla/5.0 (compatible; kumamoto-site-check/1.0)"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.references: list[tuple[str, str]] = []
        self.external_links: set[str] = set()
        self.canonical: list[str] = []
        self.og_url: list[str] = []
        self.deadlines: list[tuple[str, str]] = []
        self.blank_link_errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if values.get("id"):
            self.ids.append(values["id"])
        if values.get("data-deadline"):
            self.deadlines.append((values.get("id", tag), values["data-deadline"]))

        for attribute in ("href", "src"):
            value = values.get(attribute)
            if value:
                self.references.append((attribute, value))

        href = values.get("href", "")
        if tag == "a" and href.startswith(("http://", "https://")):
            self.external_links.add(href)
        if tag == "a" and values.get("target") == "_blank":
            rel = set(values.get("rel", "").split())
            if "noopener" not in rel:
                self.blank_link_errors.append(href or "<missing href>")
        if tag == "link" and "canonical" in values.get("rel", "").split():
            self.canonical.append(href)
        if tag == "meta" and values.get("property") == "og:url":
            self.og_url.append(values.get("content", ""))


def parse_pages() -> tuple[dict[str, PageParser], dict[str, str]]:
    parsers: dict[str, PageParser] = {}
    sources: dict[str, str] = {}
    for filename in FILES:
        source = (ROOT / filename).read_text(encoding="utf-8")
        parser = PageParser()
        parser.feed(source)
        parsers[filename] = parser
        sources[filename] = source
    return parsers, sources


def local_target(source_file: str, reference: str) -> tuple[Path, str] | None:
    parts = urlsplit(reference)
    if parts.scheme or reference.startswith(("mailto:", "tel:", "data:")):
        return None
    raw_path = unquote(parts.path)
    if raw_path.startswith("/kumamoto/"):
        raw_path = raw_path.removeprefix("/kumamoto/")
    elif raw_path.startswith("/"):
        return None
    source_path = ROOT / source_file
    target = (source_path.parent / (raw_path or source_path.name)).resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        raise ValueError(f"path escapes repository: {reference}")
    return target, unquote(parts.fragment)


def run_static_checks(parsers: dict[str, PageParser], sources: dict[str, str]) -> list[str]:
    errors: list[str] = []
    today = datetime.now(timezone(timedelta(hours=9))).date()
    ids_by_path = {str((ROOT / name).resolve()): set(parser.ids) for name, parser in parsers.items()}

    for filename, parser in parsers.items():
        duplicates = sorted({item for item in parser.ids if parser.ids.count(item) > 1})
        if duplicates:
            errors.append(f"{filename}: duplicate ids: {', '.join(duplicates)}")
        if parser.blank_link_errors:
            errors.append(f"{filename}: target=_blank without noopener: {', '.join(parser.blank_link_errors)}")
        expected = EXPECTED_URLS[filename]
        if parser.canonical != [expected]:
            errors.append(f"{filename}: canonical must be {expected}")
        if parser.og_url != [expected]:
            errors.append(f"{filename}: og:url must be {expected}")

        for _, reference in parser.references:
            try:
                resolved = local_target(filename, reference)
            except ValueError as exc:
                errors.append(f"{filename}: {exc}")
                continue
            if resolved is None:
                continue
            target, fragment = resolved
            if not target.exists():
                errors.append(f"{filename}: missing local target {reference}")
                continue
            if fragment and target.suffix.lower() == ".html":
                target_ids = ids_by_path.get(str(target))
                if target_ids is not None and fragment not in target_ids:
                    errors.append(f"{filename}: missing fragment target {reference}")

        for label, value in parser.deadlines:
            try:
                deadline = date.fromisoformat(value)
            except ValueError:
                errors.append(f"{filename}: invalid data-deadline on {label}: {value}")
                continue
            if deadline < today:
                errors.append(f"{filename}: deadline has passed on {label}: {value}")
            elif deadline <= today + timedelta(days=7):
                errors.append(f"{filename}: deadline needs review within 7 days on {label}: {value}")

        if "—" in sources[filename] or "–" in sources[filename]:
            errors.append(f"{filename}: contains a prohibited em/en dash")

    resident = sources["resident.html"]
    card_count = len(re.findall(r'<article class="[^"]*support-card[^"]*"[^>]*data-categories=', resident))
    count_match = re.search(r"すべての支援を見る（(\d+)件）", resident)
    shown_count = int(count_match.group(1)) if count_match else -1
    if card_count != shown_count:
        errors.append(f"resident.html: active card count is {card_count}, label says {shown_count}")

    robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
    if f"Sitemap: {BASE_URL}sitemap.xml" not in robots:
        errors.append("robots.txt: sitemap URL is missing or incorrect")
    try:
        sitemap = ET.parse(ROOT / "sitemap.xml")
        locations = {node.text for node in sitemap.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}
        if locations != set(EXPECTED_URLS.values()):
            errors.append("sitemap.xml: public page URLs do not match the expected set")
    except ET.ParseError as exc:
        errors.append(f"sitemap.xml: invalid XML: {exc}")

    return errors


def request_json(url: str, body: bytes) -> dict:
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "text/html; charset=utf-8", "User-Agent": USER_AGENT},
        method="POST",
    )
    with urlopen(request, timeout=60, context=ssl.create_default_context()) as response:
        return json.load(response)


def run_nu_validation(sources: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for filename, source in sources.items():
        try:
            report = request_json("https://validator.w3.org/nu/?out=json", source.encode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            errors.append(f"{filename}: Nu validator unavailable: {exc}")
            continue
        for message in report.get("messages", []):
            if message.get("type") == "error":
                errors.append(f"{filename}:{message.get('lastLine', '?')}: {message.get('message', 'HTML error')}")
    return errors


def link_status(url: str) -> int:
    last_error: Exception | None = None
    for attempt in range(2):
        for method in ("HEAD", "GET"):
            try:
                headers = {"User-Agent": USER_AGENT}
                if method == "GET":
                    headers["Range"] = "bytes=0-1023"
                request = Request(url, headers=headers, method=method)
                with urlopen(request, timeout=30, context=ssl.create_default_context()) as response:
                    return response.status
            except HTTPError as exc:
                last_error = exc
                if exc.code not in (403, 405):
                    break
            except (URLError, TimeoutError) as exc:
                last_error = exc
        if attempt == 0:
            time.sleep(2)
    raise RuntimeError(str(last_error or "unknown link error"))


def run_external_link_check(parsers: dict[str, PageParser]) -> list[str]:
    errors: list[str] = []
    links = sorted({url for parser in parsers.values() for url in parser.external_links if not url.startswith(BASE_URL)})
    for url in links:
        try:
            status = link_status(url)
            print(f"LINK {status} {url}")
        except RuntimeError as exc:
            errors.append(f"external link failed: {url} ({exc})")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nu", action="store_true", help="validate HTML with the W3C Nu service")
    parser.add_argument("--external-links", action="store_true", help="check every external anchor")
    args = parser.parse_args()

    pages, sources = parse_pages()
    errors = run_static_checks(pages, sources)
    if args.nu:
        errors.extend(run_nu_validation(sources))
    if args.external_links:
        errors.extend(run_external_link_check(pages))

    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 1
    print("PASS site quality checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
