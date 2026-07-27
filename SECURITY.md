# Security

- Never commit `.env`, SMTP passwords, API credentials, or recipient addresses.
- Use a dedicated SMTP credential with the least privileges possible.
- Publisher pages, RSS content, metadata, and LinkedIn posts are untrusted input.
- The pipeline does not execute article text, follow embedded instructions, call shell
  commands from content, or let content change recipients and configuration.
- HTML is escaped before rendering; only normalized HTTP(S) links are emitted.
- The app does not bypass paywalls, CAPTCHAs, robots controls, or LinkedIn authentication.
- LinkedIn monitoring uses explicitly configured public URLs. An organization may replace
  that adapter with an approved LinkedIn integration under its own agreement.
- The container runs as an unprivileged user with a read-only configuration mount.
- Logs contain source failures but not SMTP passwords or full message contents.

## Secret rotation

Update `/opt/semiconductor-news-brief/.env`, run `docker compose run --rm semibrief
send-test`, then revoke the old credential. Ensure the file mode is `600`.

## Dependency and image maintenance

Use Dependabot or a monthly dependency review. Rebuild and test before deployment. Pin the
LibreTranslate image by digest in high-assurance environments.

