from typing import Annotated, cast

from fastapi import Depends, Request

from woassi.modules.shops.application.facade import ShopsUseCases


def get_shops(request: Request) -> ShopsUseCases:
    return cast(ShopsUseCases, request.app.state.container)


ShopsDep = Annotated[ShopsUseCases, Depends(get_shops)]
