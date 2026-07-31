# Architecture

## Data flow

1. The scheduler starts one locked process at 08:00 Asia/Singapore.
2. The coverage window begins 24 hours before the first run, then uses the last
   successful SMTP acceptance with a two-hour overlap.
3. Adapters collect public metadata and links from GDELT, Google News RSS, direct
   publisher RSS feeds, and explicitly configured public LinkedIn post URLs.
4. Non-English items are translated only when a self-hosted LibreTranslate endpoint
   is configured. Otherwise they are excluded from the English brief.
5. URL normalization, headline similarity, and sent fingerprints remove duplicates.
6. Transparent keyword, source, freshness, company, topic, and regional weights rank
   the remaining stories. A coverage-mix selector builds the ten-story general brief,
   protecting mature-node/specialty coverage and limiting leading-edge items. Separate
   selectors then append up to three packaging and three semiconductor-technology
   updates without consuming general-news slots.
7. Deterministic sentence extraction creates up to two factual bullets. A topic-specific
   template adds the "Why it matters" line. Packaging and manufacturing-technology
   addenda are rendered after the complete general brief.
8. The renderer produces plain text, HTML, and JSON. SMTP sends a multipart email.
9. Only successful SMTP acceptance advances the last-success timestamp.

No language model is called. No model account or token is required.

## Components

- `discovery.py`: RSS, GDELT, Google News, and public LinkedIn URL adapters
- `editor.py`: translation routing, classification, ranking, clustering, extraction
- `database.py`: SQLite state, sent-story fingerprints, brief records, feedback
- `render.py`: accessible plain-text and HTML email generation
- `mailer.py`: TLS/SSL SMTP
- `pipeline.py`: orchestration, locking, idempotency, archive writing
- `cli.py`: run, dry-run, health, SMTP test, and feedback commands

## Ranking

The score is additive and inspectable:

- source priority: `priority × 1.2`
- materiality keywords: `0.8–3.0` per matched term
- preferred companies: `+0.8`, capped at `+3.0`
- preferred topics: `+0.6`, capped at `+2.0`
- priority-region match: `+0.7`
- freshness: up to `+2.0`
- unverified LinkedIn penalty: `-2.0`
- excluded-topic match: `-20`

Mature/specialty tags cover 40/45/55/65/90/110/130/180 nm families, MEMS and sensors,
power devices, analog/mixed-signal, photonics/RF, automotive, and relevant materials.
Separate packaging and standard front-end tags keep manufacturing technology visible.
The exact mix is editable in `config/interests.yml`.

`CRITICAL >= 13`, `HIGH >= 9`, and `WATCH < 9`. Items below 5 are discarded.

## Trade-offs

Deterministic extractive summaries cost nothing and never invent facts, but they are less
fluent than model-generated summaries. Paywalled sources may provide only headlines and
feed excerpts. LinkedIn discovery is intentionally limited because general company-post
retrieval requires restricted permissions; the safe default is an operator-maintained list
of direct public post URLs.
