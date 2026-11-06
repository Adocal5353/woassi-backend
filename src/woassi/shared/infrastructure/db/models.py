"""Import every model so that Alembic sees the full metadata.

Reserved for migrations/env.py: no module may import this file, it links them all.
"""

from woassi.modules.accounts.infrastructure import models as _accounts_models
from woassi.modules.catalog.infrastructure import models as _catalog_models
from woassi.shared.infrastructure import audit as _audit
from woassi.shared.infrastructure import idempotency as _idempotency
from woassi.shared.infrastructure.db.base import Base

__all__ = ["_accounts_models", "_audit", "_catalog_models", "_idempotency", "metadata"]

metadata = Base.metadata
