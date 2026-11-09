"""Import every model so that Alembic sees the full metadata.

Reserved for migrations/env.py: no module may import this file, it links them all.
"""

from woassi.modules.accounts.infrastructure import models as _accounts_models
from woassi.modules.catalog.infrastructure import models as _catalog_models
from woassi.modules.messaging.infrastructure import models as _messaging_models
from woassi.modules.shops.infrastructure import models as _shops_models
from woassi.shared.infrastructure import audit as _audit
from woassi.shared.infrastructure import idempotency as _idempotency
from woassi.shared.infrastructure.db.base import Base

__all__ = [
    "_accounts_models",
    "_audit",
    "_catalog_models",
    "_idempotency",
    "_messaging_models",
    "_shops_models",
    "metadata",
]

metadata = Base.metadata
