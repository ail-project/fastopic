#!/usr/bin/env python3
"""Minimal Flask API for querying generated poppy bloom filters."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

WORD_PATTERN = re.compile(r"[\w']+", flags=re.UNICODE)


@dataclass
class BloomIndex:
    filters: dict[str, Any]
    source_dir: Path

    def query_one(self, filter_name: str, topic: str) -> bool:
        bloom = self.filters[filter_name]
        if hasattr(bloom, "contains_str"):
            return bool(bloom.contains_str(topic))
        if hasattr(bloom, "contains"):
            return bool(bloom.contains(topic))
        if hasattr(bloom, "__contains__"):
            return topic in bloom
        raise TypeError(f"Unsupported bloom filter implementation for {filter_name!r}")

    def query_many(self, topic: str, filter_names: list[str] | None = None) -> dict[str, bool]:
        names = filter_names or sorted(self.filters)
        return {name: self.query_one(name, topic) for name in names}


def tokenize_text(text: str) -> list[str]:
    return [match.group(0).lower() for match in WORD_PATTERN.finditer(text)]


def summarize_matches(
    bloom_index: BloomIndex,
    tokens: list[str],
    filter_names: list[str],
    top_n: int,
) -> dict[str, Any]:
    token_counts = Counter(tokens)
    total_tokens = len(tokens)
    matching_tokens_by_filter: dict[str, list[tuple[str, int]]] = {}

    for filter_name in filter_names:
        matching_tokens = [
            (token, count)
            for token, count in token_counts.items()
            if bloom_index.query_one(filter_name, token)
        ]
        matching_tokens_by_filter[filter_name] = sorted(
            matching_tokens,
            key=lambda item: (-item[1], item[0]),
        )

    match_counts = {
        filter_name: sum(count for _token, count in matching_tokens_by_filter[filter_name])
        for filter_name in filter_names
    }
    match_ratios = {
        filter_name: (count / total_tokens if total_tokens else 0.0)
        for filter_name, count in match_counts.items()
    }
    top_filters = [
        {
            "filter": filter_name,
            "count": count,
            "ratio": match_ratios[filter_name],
            "matching_words": [
                {"word": token, "count": token_count}
                for token, token_count in matching_tokens_by_filter[filter_name]
            ],
        }
        for filter_name, count in sorted(match_counts.items(), key=lambda item: (-item[1], item[0]))[:top_n]
    ]
    return {"filter_counts": match_counts, "filter_ratios": match_ratios, "top_filters": top_filters}


def iter_bloom_files(filters_dir: Path) -> list[Path]:
    return sorted(path for path in filters_dir.rglob("*.poppy") if path.is_file())


def normalize_filter_name(filters_dir: Path, bloom_file: Path) -> str:
    return bloom_file.relative_to(filters_dir).with_suffix("").as_posix()


def load_bloom_file(path: Path) -> Any:
    import poppy

    bloom_cls = poppy.BloomFilter

    if hasattr(poppy, "load"):
        loaded = poppy.load(path.as_posix())
        if loaded is not None:
            return loaded

    if hasattr(bloom_cls, "load"):
        try:
            loaded = bloom_cls.load(path.as_posix())
            if loaded is not None:
                return loaded
        except TypeError:
            pass

    # Fallback for implementations where `load` is an instance method.
    bloom = bloom_cls(1, 0.01)
    if hasattr(bloom, "load"):
        loaded = bloom.load(path.as_posix())
        return loaded if loaded is not None else bloom

    raise RuntimeError("Unable to load bloom filters with this installed poppy version")


def load_bloomfilters(filters_dir: Path) -> BloomIndex:
    bloom_files = iter_bloom_files(filters_dir)
    if not bloom_files:
        raise FileNotFoundError(f"No .poppy bloom filters found under {filters_dir}")

    filters: dict[str, Any] = {}
    for bloom_file in bloom_files:
        filters[normalize_filter_name(filters_dir, bloom_file)] = load_bloom_file(bloom_file)

    return BloomIndex(filters=filters, source_dir=filters_dir)


def create_app(filters_dir: Path) -> Flask:
    app = Flask(__name__)

    try:
        bloom_index = load_bloomfilters(filters_dir)
    except Exception as exc:  # pragma: no cover - runtime startup error path
        raise RuntimeError(
            f"Unable to load bloom filters from {filters_dir}. Ensure .poppy files exist and poppy is installed."
        ) from exc

    def normalize_query_text(value: str | None) -> str:
        return (value or "").strip().lower()

    @app.get("/health")
    def health() -> Any:
        return jsonify({"status": "ok", "filter_count": len(bloom_index.filters)})

    @app.get("/api/filters")
    def list_filters() -> Any:
        return jsonify(
            {
                "source_dir": bloom_index.source_dir.as_posix(),
                "filters": sorted(bloom_index.filters),
            }
        )

    @app.get("/api/query")
    def query_filter() -> Any:
        topic = normalize_query_text(request.args.get("topic"))
        filter_name = normalize_query_text(request.args.get("filter")) or None

        if not topic:
            return jsonify({"error": "Missing required query parameter: topic"}), 400

        if filter_name:
            if filter_name not in bloom_index.filters:
                return jsonify({"error": f"Unknown filter: {filter_name}"}), 404
            return jsonify(
                {
                    "topic": topic,
                    "results": {filter_name: bloom_index.query_one(filter_name, topic)},
                }
            )

        return jsonify({"topic": topic, "results": bloom_index.query_many(topic)})

    @app.post("/api/query")
    def query_filters_bulk() -> Any:
        payload = request.get_json(silent=True) or {}
        topic = normalize_query_text(str(payload.get("topic", "")))
        requested = payload.get("filters")

        if not topic:
            return jsonify({"error": "JSON body must include a non-empty 'topic' value"}), 400

        filter_names: list[str] | None = None
        if requested is not None:
            if not isinstance(requested, list) or any(not isinstance(name, str) for name in requested):
                return jsonify({"error": "'filters' must be an array of strings"}), 400
            requested = [normalize_query_text(name) for name in requested]
            missing = sorted(name for name in requested if name not in bloom_index.filters)
            if missing:
                return jsonify({"error": "Unknown filters", "unknown_filters": missing}), 404
            filter_names = requested

        return jsonify({"topic": topic, "results": bloom_index.query_many(topic, filter_names)})

    @app.post("/api/query-text")
    def query_text() -> Any:
        payload = request.get_json(silent=True) or {}
        text = str(payload.get("text", ""))
        requested = payload.get("filters")
        top_n = payload.get("top_n", 10)

        if not text.strip():
            return jsonify({"error": "JSON body must include a non-empty 'text' value"}), 400
        if not isinstance(top_n, int) or top_n < 1:
            return jsonify({"error": "'top_n' must be a positive integer"}), 400

        filter_names = sorted(bloom_index.filters)
        if requested is not None:
            if not isinstance(requested, list) or any(not isinstance(name, str) for name in requested):
                return jsonify({"error": "'filters' must be an array of strings"}), 400
            requested = [normalize_query_text(name) for name in requested]
            missing = sorted(name for name in requested if name not in bloom_index.filters)
            if missing:
                return jsonify({"error": "Unknown filters", "unknown_filters": missing}), 404
            filter_names = requested

        tokens = tokenize_text(text)
        summary = summarize_matches(bloom_index, tokens, filter_names, min(top_n, len(filter_names)))

        return jsonify(
            {
                "text": text,
                "token_count": len(tokens),
                "unique_token_count": len(set(tokens)),
                "analyzed_filters": filter_names,
                **summary,
            }
        )

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Flask API for querying poppy bloom filters")
    parser.add_argument(
        "--filters-dir",
        type=Path,
        default=Path("bloomfilters"),
        help="Directory containing .poppy bloom filters (default: bloomfilters)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", default=5000, type=int, help="Port to listen on (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = create_app(args.filters_dir)
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
