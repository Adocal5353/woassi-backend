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

## Pitfalls

- **A module's api never imports `woassi.container`**: it imports every module, which breaks the
  `independence` contract through an indirect import. Each module declares a `<Module>UseCases`
  Protocol in `application/facade.py`, which `Container` inherits from; the api gets it from
  `request.app.state.container`. New use case: add it to both the Protocol and the Container.
- `shared/infrastructure/db/models.py` imports every model and is reserved for `migrations/env.py`.
  Every new model must be added there, otherwise Alembic will not see it.
- After a hand-written migration, `uv run alembic check` must report no drift.
- `ProductRepository.list` shadows the `list` builtin inside its class: annotate with `Sequence`.
- `lint-imports` caches by mtime: use `--no-cache` when testing a contract by reverting a file.
- Never log a WhatsApp message's sender or content. arq logs the repr of job arguments:
  `MetaEvent` hides those fields (`repr=False`), so do not replace it with a dict.

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

Only `catalog` and `messaging` contain code. `accounts`, `shops`, `customers`, `orders`, `billing`
and `payments` are empty packages. No real authentication: see the TODOs in `shared/api/deps.py`.
No calls to Meta or the payment aggregator.
