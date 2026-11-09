from typing import Annotated, cast

from fastapi import Depends, Request

from woassi.modules.customers.application.facade import CustomersUseCases


def get_customers(request: Request) -> CustomersUseCases:
    return cast(CustomersUseCases, request.app.state.container)


CustomersDep = Annotated[CustomersUseCases, Depends(get_customers)]
