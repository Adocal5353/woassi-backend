# woassi-backend
Platforme B2B2C via whatsapp

Woassi backend: WhatsApp commerce for Togolese merchants. FastAPI, PostgreSQL, Redis (arq) and
MinIO, as a modular monolith. The architecture rules are in [CLAUDE.md](CLAUDE.md).

## Getting started

Requirements: [uv](https://docs.astral.sh/uv/) and Docker.

```bash
cp .env.example .env
uv sync
docker compose up -d          # api, worker, postgres, redis, minio, minio-init
uv run alembic upgrade head
curl localhost:8000/health
```

API docs: <http://localhost:8000/docs>. MinIO console: <http://localhost:9001>.

The Compose Postgres is exposed on host port `5433`, to avoid clashing with a local PostgreSQL.

## Running the API and worker outside Docker

```bash
docker compose up -d postgres redis minio minio-init
uv run uvicorn woassi.main:create_app --factory --reload
uv run arq woassi.worker.WorkerSettings
```

## Checks

```bash
uv run ruff check . && uv run ruff format --check .
uv run lint-imports
uv run pytest                 # unit and e2e
uv run pytest -m integration  # real MinIO, needs Docker
uv run mypy src
```

To run them on every commit: `uv run pre-commit install`.

## Troubleshooting

**The Docker build hangs on `apt-get update`.** Containers have no DNS, which happens behind a
local resolver (`systemd-resolved`, Cloudflare WARP). To check:
`docker run --rm alpine nslookup deb.debian.org`.

- Lasting fix: set `{"dns": ["1.1.1.1", "8.8.8.8"]}` in `/etc/docker/daemon.json`, then run
  `sudo systemctl restart docker`.
- Workaround without `sudo`: `docker build --network host -t woassi-api:dev .`, then
  `docker compose up -d`, which reuses the image.
