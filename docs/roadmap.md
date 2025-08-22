\# Roadmap



\## Near-term

\- Add minimal application service (Python API or worker) to docker-compose.

\- Add integration/e2e tests once app exists.

\- Start tracking performance with pg\_stat\_statements dashboards.



\## Nice-to-haves

\- Use a secrets manager for production (AWS Secrets Manager / Doppler / Vault).

\- Add Bandit (Python security linter) to pre-commit and CI.

\- Add Prometheus + Grafana for DB metrics.

\- Add lint rules for SQL (sqlfluff) if/when you add lots of raw SQL.



\## Documentation

\- Keep `docs/overview.md` as the “how it’s built” source of truth.

\- Expand `docs/dev-notes.md` with common gotchas.



