from typing import Annotated, cast

from fastapi import Depends, Request

from woassi.modules.messaging.application.facade import MessagingUseCases


def get_messaging(request: Request) -> MessagingUseCases:
    return cast(MessagingUseCases, request.app.state.container)


MessagingDep = Annotated[MessagingUseCases, Depends(get_messaging)]
