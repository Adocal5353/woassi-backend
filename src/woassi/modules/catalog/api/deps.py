from typing import Annotated, cast

from fastapi import Depends, Request

from woassi.modules.catalog.application.facade import CatalogUseCases


def get_catalog(request: Request) -> CatalogUseCases:
    return cast(CatalogUseCases, request.app.state.container)


CatalogDep = Annotated[CatalogUseCases, Depends(get_catalog)]
