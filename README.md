# SemiBrief

SemiBrief creates and emails a daily executive semiconductor-industry news brief without
an LLM, OpenAI account, or per-run token cost. It discovers public reporting through
GDELT, RSS, Google News RSS, and configured public LinkedIn URLs; applies deterministic
ranking and duplicate clustering; and produces extractive English bullet summaries.

## What it monitors

The source configuration prioritizes Taipei Times, DigiTimes, Korea Herald, Yonhap,
South China Morning Post, Straits Times, The Star, Handelsblatt, Reuters, Financial
Times, EE Times, Semiconductor Engineering, IEEE Spectrum, US and European institutions,
and relevant French, UK, Italian, Swiss, Swedish, Dutch, and Belgian sources.

Some publications are paywalled or do not expose stable feeds. GDELT may discover their
public headlines and canonical links, but SemiBrief never bypasses access controls. The
optional Google News RSS fallback is disabled by default because it may return aggregator
links rather than canonical publisher URLs. Source coverage is best-effort and logged.

## Cost model

- No LLM calls and no model tokens
- GDELT and configured RSS feeds require no key
- Optional self-hosted LibreTranslate uses compute, not model tokens
- Normal VPS and SMTP provider costs may still apply

## Local setup

Requires Python 3.12 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
semibrief --config-dir config health
semibrief --config-dir config run --dry-run
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

Dry-run outputs are written under `out/` and no email is sent.

## Email configuration

Copy `.env.example` to `.env` and set:

- `SMTP_HOST`, `SMTP_PORT`
- `SMTP_USERNAME`, `SMTP_PASSWORD` when authentication is required
- `SMTP_STARTTLS=true` for port 587, or `SMTP_SSL=true` for port 465
- `EMAIL_FROM`, `EMAIL_TO`

Then test SMTP:

```bash
docker compose run --rm semibrief send-test
```

No source or LLM API key is required. `LIBRETRANSLATE_URL` is optional.

## LinkedIn

Add direct public post URLs to `config/linkedin_urls.yml`, marking responsible company or
institution accounts as `official: true`. SemiBrief will not log in or scrape profiles.
Unverified LinkedIn-only posts are placed in Radar with a warning.

LinkedIn's official Posts API has restricted organization/member permissions. If your
organization has approved access, implement an adapter under that agreement; do not put
access tokens in YAML.

## Translation

The main source set is English-first. Without a translation service, non-English GDELT
items are excluded so the email remains English-only. To translate locally without LLM
tokens:

```bash
docker compose --profile translation up -d libretranslate
```

Set `LIBRETRANSLATE_URL=http://libretranslate:5000` in `.env`. The first start downloads
language resources and can use significant memory and disk.

## VPS deployment

Ubuntu/Debian example:

```bash
sudo mkdir -p /opt/semiconductor-news-brief
sudo chown "$USER":"$USER" /opt/semiconductor-news-brief
git clone https://github.com/YOUR_ORG/YOUR_REPO.git /opt/semiconductor-news-brief
cd /opt/semiconductor-news-brief
cp .env.example .env
chmod 600 .env
# Edit .env with SMTP values.
docker compose build
docker compose run --rm semibrief health
docker compose run --rm semibrief run --dry-run
docker compose run --rm semibrief send-test
```

Install the preferred systemd schedule:

```bash
sudo cp deploy/semibrief.service deploy/semibrief.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now semibrief.timer
systemctl list-timers semibrief.timer
```

The timer fires at 00:00 UTC, which is 08:00 Singapore time. Singapore has no daylight
saving time. `Persistent=true` runs a missed job after the VPS returns.

Cron is provided in `deploy/semibrief.cron` as a fallback. Do not enable both schedulers.

## Operations

```bash
journalctl -u semibrief.service -n 200 --no-pager
docker compose run --rm semibrief health
docker compose run --rm semibrief run --dry-run
semibrief --config-dir config feedback STORY_FINGERPRINT more_like_this
```

The JSON archive records story fingerprints and scores. Edit `config/interests.yml` to
change company/topic weights and story limits.

### Backup

Stop the timer briefly and copy the named Docker volume:

```bash
sudo systemctl stop semibrief.timer
docker run --rm -v semiconductor-news-brief_semibrief-data:/data \
  -v "$PWD/backups:/backup" alpine \
  tar czf /backup/semibrief-$(date +%F).tgz -C /data .
sudo systemctl start semibrief.timer
```

Keep backups outside the VPS as appropriate.

### Upgrade and rollback

```bash
git fetch --tags
git checkout NEW_TAG
docker compose build --pull
docker compose run --rm semibrief health
docker compose run --rm semibrief run --dry-run
```

Rollback by checking out the prior tag and rebuilding. Back up the SQLite volume before
upgrades that change the schema.

## Quality checks

```bash
ruff format --check .
ruff check .
mypy
pytest --cov=semibrief --cov-report=term-missing
docker build -t semibrief:test .
```

CI uses fixtures and never makes live publisher requests.

## Known limitations

- Public feeds and GDELT coverage can change without notice.
- GDELT asks clients to limit requests; the app makes one daily search with bounded retries.
- Extractive summaries depend on the accessible headline/feed excerpt.
- Automatic machine translation requires the optional local service.
- LinkedIn does not provide unrestricted search access through its official API.
- The first real run should be reviewed before enabling delivery.
