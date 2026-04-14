# fastopic

Fastopic is a lightweight topic-classification project that uses **Bloom filters** to do very fast membership checks on text labels/topics.

The repository includes:

- Topic dictionaries (`topic/**/*.txt`)
- Utilities to normalize and compile those dictionaries into `.poppy` Bloom filters
- A small Flask API to query one or many Bloom filters

---

## How it works

1. You maintain plain text files under `topic/` (one topic per line).
2. `tools/create_bloomfilters.py` reads those files and builds Bloom filters:
   - one `.poppy` file per topic list
   - one `combined.poppy` file containing all unique entries
3. `server.py` loads all `.poppy` files in `bloomfilters/` and exposes an HTTP API.

Because Bloom filters are probabilistic data structures, lookups are very fast and memory efficient.

- `false` means **definitely not present**
- `true` means **probably present** (possible false positives depending on configured FPP)

---

## Project structure

```text
fastopic/
├── server.py                        # Flask API for querying bloom filters
├── requirements.txt                 # Runtime dependencies
├── topic/                           # Source topic lists (.txt)
│   └── location/
│       ├── en.txt
│       └── fr.txt
├── tools/
│   ├── cleanup_topic_lists.py       # Normalize/sort/dedupe topic files
│   └── create_bloomfilters.py       # Build .poppy files + combined outputs
└── bloomfilters/
    └── combined.txt                 # Generated combined list (example artifact)
```

---

## Requirements

- Python 3.10+
- pip

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## 1) Prepare / clean topic lists (optional but recommended)

Normalize all topic files (trim, deduplicate, sort):

```bash
python tools/cleanup_topic_lists.py --topic-dir topic
```

Check mode (non-mutating, useful in CI):

```bash
python tools/cleanup_topic_lists.py --topic-dir topic --check
```

---

## 2) Build bloom filters

Generate `.poppy` filters from `topic/` into `bloomfilters/`:

```bash
python tools/create_bloomfilters.py --topic-dir topic --output-dir bloomfilters --fpp 0.001
```

This writes:

- one filter per input file (e.g. `bloomfilters/location/en.poppy`)
- `bloomfilters/combined.txt` (all unique entries)
- `bloomfilters/combined.poppy`

---

## 3) Run the API server

```bash
python server.py --filters-dir bloomfilters --host 0.0.0.0 --port 5000
```

Optional debug mode:

```bash
python server.py --filters-dir bloomfilters --debug
```

---

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
    "location/en",
    "location/fr"
  ]
}
```

### `GET /api/query?topic=...&filter=...`

Query membership for one topic.

- `topic` (required)
- `filter` (optional). If omitted, queries all filters.

---

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

### Error example: missing topic

```bash
curl -i -s http://127.0.0.1:5000/api/query
```

---

## Notes on Bloom filter behavior

- A positive match is probabilistic.
- Tune `--fpp` in `create_bloomfilters.py` for your precision/sizing trade-off.
- Rebuild filters whenever topic lists change.

---

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

