"""Import every model so that Alembic sees the full metadata.

Reserved for migrations/env.py: no module may import this file, it links them all.
"""

from woassi.modules.catalog.infrastructure import models as _catalog_models
from woassi.shared.infrastructure.db.base import Base

__all__ = ["_catalog_models", "metadata"]

metadata = Base.metadata
