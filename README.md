# woassi-backend
Platforme B2B2C via whatsapp

Woassi backend: WhatsApp commerce for Togolese merchants. FastAPI, PostgreSQL, Redis (arq) and
MinIO, as a modular monolith. The architecture rules are in [CLAUDE.md](CLAUDE.md).

## Getting started

Requirements: [uv](https://docs.astral.sh/uv/) and Docker.

```bash
cp .env.example .env
uv sync
# Generate the encryption key and paste it into WOASSI_ENCRYPTION_KEY in .env
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Set META_APP_ID and META_APP_SECRET from the Meta App Dashboard
# Generate the JWT secret and paste it into JWT_SECRET in .env
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up -d          # api, worker, postgres, redis, minio, minio-init
uv run alembic upgrade head
curl localhost:8000/health
```

`curl localhost:8000/health/ready` also checks Postgres, Redis and MinIO, and answers 503 if one
of them is down.

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

## Authentication

```bash
curl -X POST localhost:8000/auth/register -H 'Content-Type: application/json' \
  -d '{"full_name": "Ama", "phone": "90 12 34 56", "password": "correct-horse"}'
docker compose logs api | grep verification_code    # in dev, the code goes to the logs
curl -X POST localhost:8000/auth/verify -H 'Content-Type: application/json' \
  -d '{"phone": "90 12 34 56", "code": "<code>"}'
curl -X POST localhost:8000/auth/login -H 'Content-Type: application/json' \
  -d '{"phone": "90 12 34 56", "password": "correct-horse"}'
```

The access token lasts 15 minutes and goes in `Authorization: Bearer`. The refresh token lasts 30
days, works once, and is returned both in the body and in an httpOnly cookie on `/auth`. A browser
client must not send two refreshes at once: replaying a consumed token ends the session.

Outside `APP_ENV=dev` the application refuses to start until a real code sender exists.

Behind a reverse proxy, configure uvicorn's `--forwarded-allow-ips`. Otherwise every client appears
under the proxy's IP and they all share one login rate limit.

## Connecting a WhatsApp number

The dashboard runs Meta's Embedded Signup, then sends the result to
`POST /shops/{shop_id}/whatsapp/connect`. It needs:

| Variable             | Used by   | Purpose                                                       |
| -------------------- | --------- | ------------------------------------------------------------- |
| `META_APP_ID`        | API       | exchanges the signup code, checks tokens                      |
| `META_APP_SECRET`    | API       | same, and signs webhooks                                      |
| `META_CONFIG_ID`     | dashboard | Facebook Login for Business configuration passed to `FB.login` |
| `META_GRAPH_VERSION` | API       | Graph API version, `v27.0`                                    |

On the dashboard side:

- use Embedded Signup v4 or later, as v2 and v3 are deprecated. On v4, set
  `featureType: "whatsapp_business_app_onboarding"` in `extras`; it is the default on v5;
- send `code`, `waba_id` and `phone_number_id`, plus `catalog_id` if the event has `catalog_ids`.

In the Meta App Dashboard, under **WhatsApp > Configuration**:

- callback URL: `https://<public host>/webhooks/meta`, verify token: `META_VERIFY_TOKEN`;
- subscribe to `messages`, `account_update`, `history`, `smb_app_state_sync` and
  `smb_message_echoes`.

Meta only calls public HTTPS URLs. In development, expose the API through a tunnel first, for
instance `cloudflared tunnel --url http://localhost:8000`, and use the URL it prints.

A shop goes `ACTIVE` once its number is `CONNECTED`. A worker job checks every token daily at 03:00
UTC.

## Encryption keys

Shop secrets (Meta tokens, aggregator credentials) are encrypted with Fernet. The API and the
worker refuse to start without a key.

To rotate, generate a new key and list it first, as the first key encrypts and all of them decrypt:

```bash
WOASSI_ENCRYPTION_KEYS=<new key>,<old key>
```

Once stored values are re-encrypted (`FernetSecretCipher.rotate`), remove the old key. Losing all
the keys means losing the secrets: store them in a secrets manager, never in the repository.

## Troubleshooting

**The Docker build hangs on `apt-get update`.** Containers have no DNS, which happens behind a
local resolver (`systemd-resolved`, Cloudflare WARP). To check:
`docker run --rm alpine nslookup deb.debian.org`.

- Lasting fix: set `{"dns": ["1.1.1.1", "8.8.8.8"]}` in `/etc/docker/daemon.json`, then run
  `sudo systemctl restart docker`.
- Workaround without `sudo`: `docker build --network host -t woassi-api:dev .`, then
  `docker compose up -d`, which reuses the image.
