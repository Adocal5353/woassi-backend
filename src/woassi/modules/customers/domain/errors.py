from woassi.shared.domain.errors import InvalidData, NotFound


class InvalidCustomer(InvalidData):
    code = "customers.invalid_customer"


class CustomerNotFound(NotFound):
    code = "customers.customer_not_found"
