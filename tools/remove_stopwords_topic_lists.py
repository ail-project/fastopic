#!/usr/bin/env python3
"""Remove stop words from per-language topic list files."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import stopwordsiso as stopwords

WORD_RE = re.compile(r"\w+", flags=re.UNICODE)


def normalize_line(line: str) -> str:
    return line.strip().lower()


def should_drop_entry(entry: str, language_stopwords: set[str]) -> bool:
    if entry in language_stopwords:
        return True

    tokens = WORD_RE.findall(entry)
    if tokens and all(token in language_stopwords for token in tokens):
        return True

    return False


def process_file(path: Path, check_only: bool = False) -> tuple[bool, int]:
    language = path.stem.lower()
    language_stopwords = stopwords.stopwords(language)
    if not language_stopwords:
        return False, 0

    original = path.read_text(encoding="utf-8")
    original_lines = original.splitlines()

    cleaned_lines: list[str] = []
    removed_count = 0
    for line in original_lines:
        normalized = normalize_line(line)
        if not normalized:
            continue

        if should_drop_entry(normalized, language_stopwords):
            removed_count += 1
            continue

        cleaned_lines.append(normalized)

    cleaned_lines = sorted(set(cleaned_lines), key=lambda value: value.casefold())
    cleaned_text = "\n".join(cleaned_lines) + "\n"

    if cleaned_text == original:
        return False, 0

    if check_only:
        return True, removed_count

    path.write_text(cleaned_text, encoding="utf-8")
    return True, removed_count


def iter_topic_files(topic_dir: Path) -> list[Path]:
    return sorted(path for path in topic_dir.rglob("*.txt") if path.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove language-specific stop words from topic list files."
    )
    parser.add_argument(
        "--topic-dir",
        default="topic",
        type=Path,
        help="Directory containing topic files (default: topic)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check whether files need updates; do not modify files.",
    )
    args = parser.parse_args()

    topic_dir: Path = args.topic_dir
    if not topic_dir.exists() or not topic_dir.is_dir():
        parser.error(f"Topic directory does not exist or is not a directory: {topic_dir}")

    changed_files: list[tuple[Path, int]] = []
    total_removed = 0

    for file_path in iter_topic_files(topic_dir):
        changed, removed_count = process_file(file_path, check_only=args.check)
        if changed:
            changed_files.append((file_path, removed_count))
            total_removed += removed_count

    for file_path, removed_count in changed_files:
        print(f"{file_path.as_posix()} (removed {removed_count} stop words)")

    if changed_files:
        print(f"Total removed entries: {total_removed}")

    if args.check and changed_files:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
