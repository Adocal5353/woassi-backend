# Woassi backend

WhatsApp commerce platform for Togolese merchants. An Account owns Shops; each Shop has its own
WhatsApp number, products, customers, orders and invoice numbering. A single Meta webhook routes
events by `phone_number_id`.

Woassi never holds funds. Amounts are in XOF: integers, no cents (`Amount`).

## Commands

Everything goes through `uv` (never pip or poetry).

```bash
uv run ruff check . && uv run ruff format --check .
uv run lint-imports
uv run pytest                 # unit + e2e
uv run pytest -m integration  # needs Docker
uv run mypy src
docker compose up -d && uv run alembic upgrade head
```

The Compose Postgres is exposed on host port **5433** (5432 is taken locally).

## Architecture rules (non-negotiable)

Clean architecture + modular monolith. Each module in `src/woassi/modules/` has 4 layers:
`domain`, `application`, `infrastructure`, `api`.

1. `domain` imports nothing external: dataclasses and Python types only.
2. `application` depends on the domain and on ports (`typing.Protocol`). A use case is a class
   with `async execute(...)`; its ports come through the constructor.
3. `infrastructure` implements the ports (SQLAlchemy, MinIO, httpx, arq, Pillow).
4. `api` (FastAPI routers + Pydantic schemas) calls use cases, never repositories.
5. Modules do not import each other: they talk through ports or domain events.
6. Ports are bound to adapters only in `src/woassi/container.py`.
7. All business routes are scoped under `/shops/{shop_id}/...`.

`uv run lint-imports` enforces these rules (contracts in `pyproject.toml`).

## Talking between modules

- **Synchronous call:** the consumer declares what it needs in its own `application/ports.py`
  (e.g. `orders` declares `CatalogPort.reserve_stock(...)`). The implementation lives in
  `src/woassi/integration/`, outside the modules, and calls the provider's use cases. It is bound
  in `container.py`. Modules never import `integration`, and `integration` never imports a
  module's `api` or `infrastructure`.
- **Domain events:** entities inherit from `Entity` and call `record_event(...)`. Repositories
  track saved entities with the Unit of Work's `_track`, which publishes `pull_events()` after the
  commit, and drops them on rollback. Module UoWs inherit from `SqlAlchemyUnitOfWork`.
- **Subscribers** are registered in `Container._register_subscribers`, which runs in both the API
  and the worker: `bus.subscribe(Event, handler, name="billing.issue_invoice", deferred=True)`.
  A `deferred` subscriber runs in the worker through the `dispatch_event` job. Its `name` is stored
  in queued jobs: keep it stable. An event class must be frozen and `kw_only`, and it is pickled.
- Events are delivered at most once: a crash right after a commit loses them, a failing subscriber
  is only logged, and `dispatch_event` is not retried.

## Shared foundation

- **Secrets:** always go through the `SecretCipher` port (`Container.cipher`), never store a Meta
  token or aggregator credential in clear text.
- **Audit:** `uow.audit.record(...)` before `uow.commit()`, so that the entry shares the action's
  transaction. Actions look like `order.validated`, `invoice.issued`,
  `receiving_account.updated`. The log is append-only: read it with
  `GET /shops/{shop_id}/audit-log`.
- **Webhooks and jobs:** `async with process_once(session, source, key) as is_new:` runs the block
  once per key. The key joins the caller's transaction, so the caller must commit.
- **Rate limits:** `enforce(limiter, key, limit, window_s)`, 429 with `Retry-After`.
- **Sensitive POST routes:** `dependencies=[Depends(idempotent)]` adds the optional
  `Idempotency-Key` header. Not applied to any route yet.
- **Time:** inject `Clock`, never call `datetime.now()`. Store `now()` (UTC); `local_now()`
  (Africa/Lome) is for display. Use `FrozenClock` in tests.
- **Lists:** routes return `Page[T]` built from a use case's `PageResult[T]`, with the shared
  `Offset` and `Limit` query parameters.
- **Phone numbers:** `PhoneNumber` holds E.164 only; `PhoneNormalizer` parses free-form input,
  with Togo as the default country.

## Naming

All code is in English: identifiers, classes, files, URLs, tables, error codes, messages and
comments. Prompts may use French business terms; translate them with this glossary:

| French          | Code            | French          | Code          |
| --------------- | --------------- | --------------- | ------------- |
| Compte          | Account         | Facture         | Invoice       |
| Boutique        | Shop            | Avoir           | Credit note   |
| Client          | Customer        | Paiement        | Payment       |
| Commande        | Order           | Montant         | Amount        |
| Produit         | Product         | Messagerie      | Messaging     |

API messages are for developers: a user-facing French UI should map from the stable `code`.

## Accounts and access control

- `shared/api/deps.py` provides `CurrentAccount` and `get_authorized_shop`. Every shop route uses
  `dependencies=[Depends(get_authorized_shop)]`. A foreign shop gives a 404, never a 403. Webhooks
  stay public: they check their own signature.
- `shared` cannot import `accounts` or `shops`, so it declares `AccountAuthenticator` and
  `ShopOwnershipPort`, implemented in `woassi/integration`.
- Refresh tokens: only their SHA-256 is stored. `RefreshTokenStore.consume` is one atomic UPDATE.
  Replaying a consumed token revokes its family; that revocation is committed before raising.
  Password change and reset revoke every session of the account.
- Verification codes are hashed with the password hasher. A failed attempt is committed before
  raising, otherwise it would not count.
- Login failures are neutral (`auth.invalid_credentials`), and timing too: use `dummy_verify` when
  there is nothing to compare with. Reset requests answer 202 whether or not the phone exists.
- Rate limits count failed logins only, as many users share an IP behind a mobile carrier's NAT.
  `RateLimiter.hit` comes first, as it is atomic, and `forgive` gives the attempt back on success.
- Access tokens cannot be revoked: they stay valid for up to 15 minutes after a logout.

## Shops and WhatsApp

- `Shop` is an aggregate: settings, WhatsApp account and receiving account load and save with it.
  `ShopRepository` hides archived shops, so `DELETE` leaves every route answering 404.
- A shop is `ACTIVE` only with a `CONNECTED` number; losing the number sends it back to `DRAFT`.
- `phone_number_id` comes from the browser. It is only written once Meta has confirmed it with the
  merchant's token, otherwise anyone could squat someone else's number with a fake code.
- Graph calls live in `shops/infrastructure/meta_onboarding.py`, each with a link to its doc, and
  run outside any transaction. Check the doc again when changing `META_GRAPH_VERSION`.
- **Graph secrets travel in query strings.** Never log a URL or an httpx exception. `httpx` logging
  is silenced, Sentry's httpx integration is disabled, and `MetaError` carries no Meta text.
- `MetaError` is only a shop failure when Meta says so: the daily token check ignores outages.
- Coexistence: skip `POST /{phone}/register`, and `smb_app_data` works once per sync type, within
  24 hours. Numbers not on `platform_type=CLOUD_API` are refused, as `/register` is not implemented.
- A receiving account receives the money: changing its operator or number resets `verified`.
- No FK across modules: it would tie them together, and shops and accounts are never deleted.

## Pitfalls

- **A module's api never imports `woassi.container`**: it imports every module, which breaks the
  `independence` contract through an indirect import. Each module declares a `<Module>UseCases`
  Protocol in `application/facade.py`, which `Container` inherits from; the api gets it from
  `request.app.state.container`. New use case: add it to both the Protocol and the Container.
- `shared/infrastructure/db/models.py` imports every model and is reserved for `migrations/env.py`.
  Every new model must be added there, otherwise Alembic will not see it.
- After a hand-written migration, `uv run alembic check` must report no drift.
- `ProductRepository.list` shadows the `list` builtin inside its class: annotate with `Sequence`.
- The arq worker exits when Redis goes away and relies on `restart: unless-stopped`; `/health/ready`
  only covers the API, so a dead worker does not show there.
- `lint-imports` caches by mtime: use `--no-cache` when testing a contract by reverting a file.
- Never log a WhatsApp message's sender or content. arq logs the repr of job arguments:
  `MetaEvent` hides those fields (`repr=False`), so do not replace it with a dict. The same goes
  for any domain event carrying personal data and sent to a deferred subscriber.
- `AuditLog.list` also shadows the builtin; same fix as `ProductRepository.list`.
- A Protocol the api needs goes in `application/facade.py`, including for `shared`
  (`SharedUseCases`), so a new shared use case also goes in `Container`.

## MinIO storage

| Bucket             | Access      | Content                                                       |
| ------------------ | ----------- | ------------------------------------------------------------- |
| `woassi-uploads`   | private     | dashboard originals, in transit                               |
| `woassi-products`  | public read | final WebP (Meta needs a stable URL: never a presigned one)   |
| `woassi-documents` | private     | PDF invoices and credit notes, presigned URLs                 |

Object keys:

- original: `shops/{shop_id}/products/{product_id}/originals/{photo_id}`
- final: `shops/{shop_id}/products/{product_id}/{photo_id}_{400|1024}.webp`
- invoice: `shops/{shop_id}/invoices/{number}.pdf`

## Current state

`accounts`, `catalog`, `messaging` and `shops` contain code. `customers`, `orders`, `billing` and
`payments` are empty packages. Codes are only written to the logs (`LogVerificationCodeSender`, dev
only). The Graph API is only called for onboarding; no messages are sent. No calls to the payment
aggregator.
