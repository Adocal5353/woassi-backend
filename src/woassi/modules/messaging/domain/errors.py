from woassi.shared.domain.errors import DomainError


class InvalidSignature(DomainError):
    code = "messaging.invalid_signature"


class VerificationRefused(DomainError):
    code = "messaging.verification_refused"
