from woassi.shared.domain.errors import Conflict, InvalidData, NotFound


class ProductNotFound(NotFound):
    code = "catalog.product_not_found"


class PhotoNotFound(NotFound):
    code = "catalog.photo_not_found"


class InvalidProduct(InvalidData):
    code = "catalog.invalid_product"


class InsufficientStock(Conflict):
    code = "catalog.insufficient_stock"


class RetailerIdAlreadyUsed(Conflict):
    code = "catalog.retailer_id_already_used"


class InvalidPhoto(InvalidData):
    code = "catalog.invalid_photo"


class TooManyPhotos(Conflict):
    code = "catalog.too_many_photos"


class PhotoAlreadyProcessed(Conflict):
    code = "catalog.photo_already_processed"


class UnreadableImage(InvalidData):
    code = "catalog.unreadable_image"
