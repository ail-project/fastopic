#!/usr/bin/env python3
"""Clean up topic list files by normalizing, de-duplicating, and sorting entries."""

from __future__ import annotations

import argparse
from pathlib import Path


def normalize_lines(text: str) -> list[str]:
    lines = [line.strip().lower() for line in text.splitlines()]
    lines = [line for line in lines if line]
    unique_lines = sorted(set(lines), key=lambda value: value.casefold())
    return unique_lines


def normalize_file(path: Path, check_only: bool = False) -> bool:
    original = path.read_text(encoding="utf-8")
    normalized_lines = normalize_lines(original)
    normalized = "\n".join(normalized_lines) + "\n"
    if original == normalized:
        return False

    if check_only:
        return True

    path.write_text(normalized, encoding="utf-8")
    return True


def iter_topic_files(topic_dir: Path) -> list[Path]:
    return sorted(path for path in topic_dir.rglob("*.txt") if path.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize all .txt topic files by sorting and removing duplicates."
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

    changed_files: list[Path] = []
    for file_path in iter_topic_files(topic_dir):
        if normalize_file(file_path, check_only=args.check):
            changed_files.append(file_path)

    for file_path in changed_files:
        print(file_path.as_posix())

    if args.check and changed_files:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
