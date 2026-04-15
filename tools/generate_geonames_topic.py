#!/usr/bin/env python3
"""Download GeoNames country dump files and build per-country topic files.

Each generated file contains one normalized variant name per line, including:
- `name` (column 2)
- `asciiname` (column 3)
- each value from `alternatenames` (column 4)

Input files are downloaded from https://download.geonames.org/export/dump/{COUNTRY}.zip.
"""

from __future__ import annotations

import argparse
import io
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


def parse_country_codes(raw_codes: list[str]) -> list[str]:
    parsed: set[str] = set()
    for item in raw_codes:
        for token in item.split(","):
            code = token.strip().upper()
            if not code:
                continue
            if len(code) != 2 or not code.isalpha():
                raise ValueError(f"Invalid ISO country code: {token!r}")
            parsed.add(code)
    return sorted(parsed)


def normalize_variant(value: str) -> str:
    return " ".join(value.strip().lower().split())


def extract_variants_from_geonames_bytes(content: bytes) -> set[str]:
    variants: set[str] = set()
    with io.TextIOWrapper(io.BytesIO(content), encoding="utf-8") as text_stream:
        for raw_line in text_stream:
            line = raw_line.rstrip("\n")
            if not line:
                continue
            columns = line.split("\t")
            if len(columns) < 4:
                continue

            direct_names = [columns[1], columns[2]]
            alternate_names = columns[3].split(",") if columns[3] else []

            for value in [*direct_names, *alternate_names]:
                normalized = normalize_variant(value)
                if normalized:
                    variants.add(normalized)
    return variants


def download_country_zip(country_code: str, base_url: str) -> bytes:
    url = f"{base_url.rstrip('/')}/{country_code}.zip"
    try:
        with urllib.request.urlopen(url) as response:
            return response.read()
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        raise RuntimeError(f"Failed to download {url}: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network path
        raise RuntimeError(f"Failed to download {url}: {exc.reason}") from exc


def read_country_txt_from_zip(country_code: str, zip_payload: bytes) -> bytes:
    expected_txt = f"{country_code}.txt"
    with zipfile.ZipFile(io.BytesIO(zip_payload)) as archive:
        try:
            with archive.open(expected_txt) as country_file:
                return country_file.read()
        except KeyError as exc:
            raise RuntimeError(
                f"Archive for {country_code} does not contain expected file {expected_txt}"
            ) from exc


def write_country_topic_file(output_dir: Path, country_code: str, variants: set[str]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / f"{country_code.lower()}.txt"
    sorted_variants = sorted(variants, key=lambda value: value.casefold())
    target_path.write_text("\n".join(sorted_variants) + "\n", encoding="utf-8")
    return target_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Download GeoNames country ZIP dumps and generate topic/geonames/*.txt "
            "files containing all geographic name variants."
        )
    )
    parser.add_argument(
        "country_codes",
        nargs="+",
        help="ISO country codes (space and/or comma separated), e.g. 'BE NL' or 'BE,NL'",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("topic") / "geonames",
        help="Directory where per-country topic files are written (default: topic/geonames)",
    )
    parser.add_argument(
        "--base-url",
        default="https://download.geonames.org/export/dump",
        help="Base URL for GeoNames dump files (default: https://download.geonames.org/export/dump)",
    )
    args = parser.parse_args()

    try:
        country_codes = parse_country_codes(args.country_codes)
    except ValueError as exc:
        parser.error(str(exc))

    for country_code in country_codes:
        zip_payload = download_country_zip(country_code, args.base_url)
        country_txt_payload = read_country_txt_from_zip(country_code, zip_payload)
        variants = extract_variants_from_geonames_bytes(country_txt_payload)
        target = write_country_topic_file(args.output_dir, country_code, variants)
        print(f"{country_code}: {len(variants)} variants -> {target.as_posix()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
