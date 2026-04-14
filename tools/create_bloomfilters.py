#!/usr/bin/env python3
"""Create poppy bloom filters for each topic list plus a combined bloom filter."""

from __future__ import annotations

import argparse
from pathlib import Path

import poppy


def normalize_entries(text: str) -> list[str]:
    entries = [line.strip() for line in text.splitlines()]
    entries = [entry for entry in entries if entry]
    return sorted(set(entries), key=lambda value: value.casefold())


def iter_topic_files(topic_dir: Path) -> list[Path]:
    return sorted(path for path in topic_dir.rglob("*.txt") if path.is_file())


def build_filter(entries: list[str], fpp: float) -> poppy.BloomFilter:
    capacity = max(1, len(entries))
    bloom = poppy.BloomFilter(capacity, fpp)
    for entry in entries:
        bloom.insert_str(entry)
    return bloom


def output_path(topic_dir: Path, output_dir: Path, topic_file: Path) -> Path:
    relative = topic_file.relative_to(topic_dir)
    return (output_dir / relative).with_suffix(".poppy")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create .poppy bloom filters for topic lists and one combined bloom filter.",
    )
    parser.add_argument(
        "--topic-dir",
        type=Path,
        default=Path("topic"),
        help="Directory containing .txt topic lists (default: topic)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("bloomfilters"),
        help="Directory where bloom filters and combined list will be written (default: bloomfilters)",
    )
    parser.add_argument(
        "--fpp",
        type=float,
        default=0.001,
        help="False positive probability for generated bloom filters (default: 0.001)",
    )
    args = parser.parse_args()

    if not args.topic_dir.exists() or not args.topic_dir.is_dir():
        parser.error(f"Topic directory does not exist or is not a directory: {args.topic_dir}")

    topic_files = iter_topic_files(args.topic_dir)
    if not topic_files:
        parser.error(f"No .txt topic files found under: {args.topic_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    combined_entries: set[str] = set()

    for topic_file in topic_files:
        entries = normalize_entries(topic_file.read_text(encoding="utf-8"))
        combined_entries.update(entries)

        bloom = build_filter(entries, args.fpp)
        target_path = output_path(args.topic_dir, args.output_dir, topic_file)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        bloom.save(target_path.as_posix())
        print(target_path.as_posix())

    combined_sorted = sorted(combined_entries, key=lambda value: value.casefold())
    combined_list_path = args.output_dir / "combined.txt"
    combined_list_path.write_text("\n".join(combined_sorted) + "\n", encoding="utf-8")
    print(combined_list_path.as_posix())

    combined_filter = build_filter(combined_sorted, args.fpp)
    combined_filter_path = args.output_dir / "combined.poppy"
    combined_filter.save(combined_filter_path.as_posix())
    print(combined_filter_path.as_posix())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
