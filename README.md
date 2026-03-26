# News Aggregator

Pulls news from two different APIs, runs some text analysis on what it finds, and dumps everything into structured JSON reports. Built to track Iran-related geopolitical news (strikes, energy, leadership) alongside a random sample of spaceflight headlines — two pretty different beats, handled by the same pipeline.

---

## What it actually does

Every time you run it, it:

1. Hits **GNews** with a targeted search query (`iran AND (attacks OR strikes OR energy OR leader OR damage)`) and grabs the 10 most recent results
2. Hits the **Spaceflight News API** and randomly samples 10 articles from its full archive
3. Merges and deduplicates everything by URL
4. Analyzes the combined text — word frequency, least common words, repeat authors
5. Writes two separate JSON reports (one per provider) into `gnews/` and `spaceflight/` folders

---

## Architecture

![Architecture](architecture.svg)

```
main.py
  │
  ├── config.py          loads GNEWS_API_KEY from .env
  │
  ├── transport.py       shared HTTP layer (rate limiting, retries, backoff)
  │
  ├── providers/
  │   ├── base.py        abstract NewsProvider interface
  │   ├── gnews.py       GNews API v4 — search endpoint
  │   └── spaceflight.py Spaceflight News API v4 — search + random offset sampling
  │
  ├── aggregator.py      fans out to all providers, deduplicates by URL
  ├── analyzer.py        pure text analysis — word freq, author counts
  └── reporter.py        builds the JSON report structure, writes to disk
```

The flow is linear: fetch → aggregate → analyze → report. Nothing fancy, but each piece has a single job and they compose cleanly.

---

## Each part, and why it exists

**`config.py`**
Loads secrets from a `.env` file (or from environment variables directly). Written without `python-dotenv` as a dependency — just a small custom parser. Pre-existing env vars always win over `.env` values, so CI/CD environments work without any file changes.

**`transport.py`**
All HTTP calls go through here. Handles rate limiting (minimum delay between requests), retry with exponential backoff for transient failures (429, 500, 502, 503, 504), and immediately raises on non-retriable errors (400, 404). Providers inject this as a dependency so it's easy to mock in tests.

**`providers/gnews.py`**
Wraps the GNews API v4 `/search` endpoint. Maps a `NewsQuery` to GNews params (`token`, `q`, `lang`, `max`, `sortby`, `from`, `to`). GNews doesn't return author data, so `authors` is always empty. The raw API payload is preserved in full on every article.

**`providers/spaceflight.py`**
Two modes: if a query string is given, uses the `/articles/?search=` endpoint. If no query, does random offset sampling — fetches the total count, picks N random offsets, and makes N individual requests. This is how we get a genuine random cross-section of space news rather than always the latest.

**`aggregator.py`**
Takes a list of providers, calls each with the appropriate query, collects results, and deduplicates by URL. If a provider fails, it logs a warning and continues — one broken API key shouldn't kill the whole run.

**`analyzer.py`**
Pure functions, no side effects. Takes a list of articles and returns word frequency counts and author tallies. Tokenizes by lowercasing and stripping everything that isn't a-z — simple but consistent. Completely stateless, so every function is trivially testable without mocking anything.

**`reporter.py`**
Builds the output dict and writes it to a timestamped JSON file. Each article includes both the normalized fields and the original `raw` API payload, so you can always trace back exactly what the API returned.

---

## How to run it

**1. Get a GNews API key**

Sign up at https://gnews.io — the free tier gives you 100 requests/day which is plenty.

**2. Add your key to a `.env` file**

```
GNEWS_API_KEY=your_key_here
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Run**

```bash
python main.py
```

Output lands in `gnews/` and `spaceflight/` folders, one JSON file per run, timestamped.

---

## How it's tested

```bash
pytest
# or for just one provider:
pytest tests/test_gnews.py -v
```

All tests use injected mocks — no real HTTP calls, no API key needed. The `HttpClient` is a protocol (structural typing), so any object with a `.get()` method satisfies it. This means tests just pass in a `MagicMock` and control exactly what the "API" returns.

Why mocks instead of hitting the real APIs in tests? A few reasons:

- **Speed** — the test suite runs in under a second
- **Reliability** — tests don't fail because GNews is having a bad day
- **Cost** — free tier API keys have rate limits; burning them on CI runs is wasteful
- **Determinism** — you can test exact error conditions (400s, 503s, malformed payloads) that are hard to reproduce against a real API

There's also a live integration test in `tests/test_gnews.py` that's skipped by default and only runs when `GNEWS_API_KEY` is set:

```bash
GNEWS_API_KEY=your_key pytest tests/test_gnews.py -k live_connection -v
```

---

## Example output

After a run you'll see two folders:

```
gnews/
  summary_results_quotes_20260326030058.json
spaceflight/
  summary_results_quotes_20260326030058.json
```

**`gnews/summary_results_quotes_*.json`**

```json
{
  "generated_at": "2026-03-26T03:00:58.435113",
  "article_count": 10,
  "articles": [
    {
      "provider": "gnews",
      "provider_article_id": "https://economictimes.indiatimes.com/...",
      "title": "Oman Oil prices crash 46% in 9 days...",
      "url": "https://economictimes.indiatimes.com/...",
      "source_name": "The Economic Times",
      "published_at": "2026-03-25T14:58:00Z",
      "authors": [],
      "raw": {
        "id": "179fa748411d8a7c801b1df892e29d76",
        "title": "Oman Oil prices crash 46% in 9 days...",
        "description": "Oman oil prices have crashed 46% from their peak...",
        "content": "Synopsis\nOman Oil prices crash... [9432 chars]",
        "url": "https://economictimes.indiatimes.com/...",
        "image": "https://img.etimg.com/...",
        "publishedAt": "2026-03-25T14:58:00Z",
        "lang": "en",
        "source": {
          "id": "5464668c1f0466950a0b2fab5249ec6c",
          "name": "The Economic Times",
          "url": "https://economictimes.indiatimes.com",
          "country": "in"
        }
      }
    }
  ],
  "analysis": {
    "least_common_words_containing_l": [
      { "word": "alerts", "count": 1 },
      { "word": "almost", "count": 1 },
      { "word": "alternative", "count": 1 },
      { "word": "analysts", "count": 1 },
      { "word": "barrel", "count": 1 }
    ],
    "authors_appearing_more_than_once": []
  }
}
```

**`spaceflight/summary_results_quotes_*.json`**

Same structure, different raw payload shape — Spaceflight includes `launches`, `events`, `featured`, and `updated_at` fields that GNews doesn't have:

```json
{
  "generated_at": "2026-03-26T03:00:58.435113",
  "article_count": 10,
  "articles": [
    {
      "provider": "spaceflight",
      "provider_article_id": "5790",
      "title": "China launches Haiyang-1D ocean observation satellite",
      "url": "https://spacenews.com/china-launches-haiyang-1d-ocean-observation-satellite/",
      "source_name": "SpaceNews",
      "published_at": "2020-06-10T20:13:06Z",
      "authors": [],
      "raw": {
        "id": 5790,
        "title": "China launches Haiyang-1D ocean observation satellite",
        "authors": [],
        "url": "https://spacenews.com/...",
        "image_url": "https://spacenews.com/...",
        "news_site": "SpaceNews",
        "summary": "",
        "published_at": "2020-06-10T20:13:06Z",
        "updated_at": "2021-05-18T13:46:54.467000Z",
        "featured": false,
        "launches": [
          {
            "launch_id": "93290541-91b1-4de5-9602-2da2e30480d8",
            "provider": "Launch Library 2"
          }
        ],
        "events": []
      }
    }
  ],
  "analysis": {
    "least_common_words_containing_l": [
      { "word": "bilateral", "count": 1 },
      { "word": "children", "count": 1 }
    ],
    "authors_appearing_more_than_once": []
  }
}
```

---

## Known limitations

- **GNews doesn't return author data** — the `authors` field will always be `[]` for gnews articles. The author byline exists on the article page but isn't in the API response. Would need page scraping to fix this.
- **GNews content is truncated** — the `content` field cuts off around 9-10k characters. Full text requires fetching the article URL directly.
- **Spaceflight random sampling is slow** — each random article is a separate HTTP request, so fetching 10 articles means 11 requests (1 for total count + 10 individual). Rate limiter adds a 1s delay between each.
