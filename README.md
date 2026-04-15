# fastopic

Fastopic is a lightweight topic-classification project that uses **Bloom filters** to do very fast membership checks on text labels/topics.
The current filters help quickly identify content that may contain geolocation elements before performing a full lookup on every word.

The repository includes:

- Topic dictionaries (`topic/**/*.txt`)
- Utilities to normalize and compile those dictionaries into `.poppy` Bloom filters
- A small Flask API to query one or many Bloom filters

## How it works

1. You maintain plain text files under `topic/` (one topic per line).
2. `tools/create_bloomfilters.py` reads those files and builds Bloom filters:
   - one `.poppy` file per topic list
   - one `combined.poppy` file containing all unique entries
3. `server.py` loads all `.poppy` files in `bloomfilters/` and exposes an HTTP API.

Because Bloom filters are probabilistic data structures, lookups are very fast and memory efficient.

- `false` means **definitely not present**
- `true` means **probably present** (possible false positives depending on configured FPP)


## Project structure

```text
fastopic/
├── server.py                        # Flask API for querying bloom filters
├── requirements.txt                 # Runtime dependencies
├── topic/                           # Source topic lists (.txt)
│   ├── location/
│   │   ├── en.txt
│   │   └── fr.txt
│   └── country/
│       ├── en.txt
│       └── fr.txt
├── tools/
│   ├── cleanup_topic_lists.py       # Normalize/sort/dedupe topic files
│   └── create_bloomfilters.py       # Build .poppy files + combined outputs
└── bloomfilters/
    └── combined.txt                 # Generated combined list (example artifact)
```

## Requirements

- Python 3.10+
- pip
- poppy-py

Install dependencies:

```bash
pip install -r requirements.txt
```

## 1) Prepare / clean topic lists (optional but recommended)

Normalize all topic files (trim, deduplicate, sort):

```bash
python tools/cleanup_topic_lists.py --topic-dir topic
```

Check mode (non-mutating, useful in CI):

```bash
python tools/cleanup_topic_lists.py --topic-dir topic --check
```

## 2) Build bloom filters

Generate `.poppy` filters from `topic/` into `bloomfilters/`:

```bash
python tools/create_bloomfilters.py --topic-dir topic --output-dir bloomfilters --fpp 0.001
```

This writes:

- one filter per input file (e.g. `bloomfilters/location/en.poppy`)
- `bloomfilters/combined.txt` (all unique entries)
- `bloomfilters/combined.poppy`

## 3) Run the API server

```bash
python server.py --filters-dir bloomfilters --host 0.0.0.0 --port 5000
```

Optional debug mode:

```bash
python server.py --filters-dir bloomfilters --debug
```

Context extraction tuning (for `/api/query-text`):

- `--context-min-count` (default `2`): minimum matched-token count in a filter before context extraction is emitted.
- `--context-min-ratio` (default `0.05`): minimum matched-token ratio in a filter before context extraction is emitted.
- `--context-window-words` (default `10`): words included before and after each matching token.


## 4) Generate GeoNames country topic files

You can create a dedicated `geonames` topic (one file per country) from the official GeoNames country ZIP dumps:

```bash
python tools/generate_geonames_topic.py BE NL
```

Or using comma-separated codes:

```bash
python tools/generate_geonames_topic.py BE,NL
```

Or generate files for all countries listed in GeoNames `countryInfo.txt`:

```bash
python tools/generate_geonames_topic.py --all-countries
```

This downloads `https://download.geonames.org/export/dump/{COUNTRY}.zip`, reads `{COUNTRY}.txt`, and writes normalized variants (name + asciiname + alternatenames) to:

- `topic/geonames/be.txt`
- `topic/geonames/nl.txt`

## API reference

Base URL (local): `http://127.0.0.1:5000`

### `GET /health`

Quick liveness + number of loaded filters.

Response example:

```json
{
  "status": "ok",
  "filter_count": 3
}
```

### `GET /api/filters`

List available filter names.

Response example:

```json
{
  "source_dir": "bloomfilters",
  "filters": [
    "combined",
    "country/en",
    "location/en",
    "location/fr"
  ]
}
```

### `GET /api/query?topic=...&filter=...`

Query membership for one topic.

- `topic` (required)
- `filter` (optional). If omitted, queries all filters.

### `POST /api/query-text`

Extract words from a full input text (regex tokenizer), test each token against one or more Bloom filters, and return occurrence counts per filter plus a ranked top list.  
When a filter reaches the configured count+ratio thresholds, the API also returns contextual excerpts around matching words.

JSON body:

- `text` (required): full text to analyze
- `filters` (optional): list of filter names to restrict matching
- `top_n` (optional, default `10`): number of top filters to include

Response example:

```json
{
  "text": "Paris is in France and Paris has cafes.",
  "token_count": 8,
  "unique_token_count": 7,
  "analyzed_filters": ["combined", "country/en", "location/en"],
  "context_extraction_config": {
    "min_match_count": 2,
    "min_match_ratio": 0.05,
    "window_words": 10
  },
  "potential_contexts": [
    {
      "filter": "location/en",
      "match_word": "Paris",
      "match_index": 0,
      "context_start_index": 0,
      "context_end_index": 7,
      "context": "Paris is in France and Paris has cafes"
    }
  ],
  "filter_counts": {
    "combined": 3,
    "country/en": 1,
    "location/en": 2
  },
  "top_filters": [
    {"filter": "combined", "count": 3},
    {"filter": "location/en", "count": 2},
    {"filter": "country/en", "count": 1}
  ]
}
```

## curl examples (API use cases)

### Health check

```bash
curl -s http://127.0.0.1:5000/health | jq
```

### List all available filters

```bash
curl -s http://127.0.0.1:5000/api/filters | jq
```

### Query one filter (`location/en`)

```bash
curl -sG \
  --data-urlencode "topic=paris" \
  --data-urlencode "filter=location/en" \
  http://127.0.0.1:5000/api/query | jq
```

### Query all filters for a topic

```bash
curl -sG \
  --data-urlencode "topic=paris" \
  http://127.0.0.1:5000/api/query | jq
```

### Bulk query with JSON (POST)

```bash
curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{"topic":"paris","filters":["location/en","location/fr"]}' \
  http://127.0.0.1:5000/api/query | jq
```

### Query complete text and rank matching filters

```bash
curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{"text":"Paris is in France and Paris has cafes","top_n":5}' \
  http://127.0.0.1:5000/api/query-text | jq
```

### Error example: missing topic

```bash
curl -i -s http://127.0.0.1:5000/api/query
```

## Notes on Bloom filter behavior

- A positive match is probabilistic.
- Tune `--fpp` in `create_bloomfilters.py` for your precision/sizing trade-off.
- Rebuild filters whenever topic lists change.

## Typical workflow

```bash
# 1) normalize topic lists
python tools/cleanup_topic_lists.py --topic-dir topic

# 2) build bloom filters
python tools/create_bloomfilters.py --topic-dir topic --output-dir bloomfilters --fpp 0.001

# 3) run API
python server.py --filters-dir bloomfilters --port 5000

# 4) query API
curl -sG --data-urlencode "topic=paris" http://127.0.0.1:5000/api/query
```
