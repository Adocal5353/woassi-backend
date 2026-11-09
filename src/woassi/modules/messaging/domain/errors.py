from woassi.shared.domain.errors import Conflict, DomainError, InvalidData, UpstreamError


class InvalidSignature(DomainError):
    code = "messaging.invalid_signature"


class VerificationRefused(DomainError):
    code = "messaging.verification_refused"


class InvalidMessage(InvalidData):
    code = "messaging.invalid_message"


class ShopNotConnected(Conflict):
    code = "messaging.shop_not_connected"


class OutsideCustomerServiceWindow(Conflict):
    """More than 24 hours since the customer last wrote: only an approved template can go."""

    code = "messaging.outside_customer_service_window"


class InvalidRecipient(InvalidData):
    code = "messaging.invalid_recipient"


class MessageNotSent(UpstreamError):
    code = "messaging.message_not_sent"


class TemplateNotApproved(Conflict):
    """Meta has not approved the template yet, or no longer allows it."""

    code = "messaging.template_not_approved"
