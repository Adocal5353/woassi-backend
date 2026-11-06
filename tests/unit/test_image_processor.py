from io import BytesIO

import pytest
from PIL import Image

from woassi.modules.catalog.domain.errors import UnreadableImage
from woassi.modules.catalog.infrastructure.image_processor import PillowImageProcessor

ORIENTATION = 0x0112


def jpeg(width: int, height: int, *, orientation: int | None = None) -> bytes:
    image = Image.new("RGB", (width, height), "red")
    exif = Image.Exif()
    exif[0x010F] = "Secret camera"
    if orientation is not None:
        exif[ORIENTATION] = orientation
    output = BytesIO()
    image.save(output, format="JPEG", exif=exif)
    return output.getvalue()


async def test_generates_one_webp_variant_per_size() -> None:
    variants = await PillowImageProcessor().webp_variants(jpeg(2000, 1000), (400, 1024))

    assert set(variants) == {400, 1024}
    for size, data in variants.items():
        image = Image.open(BytesIO(data))
        assert image.format == "WEBP"
        assert image.size == (size, size // 2)


async def test_does_not_upscale_small_image() -> None:
    variants = await PillowImageProcessor().webp_variants(jpeg(100, 50), (400,))
    assert Image.open(BytesIO(variants[400])).size == (100, 50)


async def test_fixes_exif_orientation() -> None:
    # Orientation 6: the image must be rotated 90° for display.
    variants = await PillowImageProcessor().webp_variants(jpeg(800, 400, orientation=6), (400,))
    assert Image.open(BytesIO(variants[400])).size == (200, 400)


async def test_strips_metadata() -> None:
    variants = await PillowImageProcessor().webp_variants(jpeg(800, 400), (400,))
    image = Image.open(BytesIO(variants[400]))
    assert "exif" not in image.info
    assert len(image.getexif()) == 0


async def test_keeps_transparency() -> None:
    output = BytesIO()
    Image.new("RGBA", (10, 10), (255, 0, 0, 0)).save(output, format="PNG")
    variants = await PillowImageProcessor().webp_variants(output.getvalue(), (400,))
    assert Image.open(BytesIO(variants[400])).mode == "RGBA"


@pytest.mark.parametrize("data", [b"", b"not an image"])
async def test_unreadable_data(data: bytes) -> None:
    with pytest.raises(UnreadableImage):
        await PillowImageProcessor().webp_variants(data, (400,))


async def test_rejects_disallowed_format() -> None:
    output = BytesIO()
    Image.new("RGB", (10, 10)).save(output, format="GIF")
    with pytest.raises(UnreadableImage):
        await PillowImageProcessor().webp_variants(output.getvalue(), (400,))


async def test_truncated_image() -> None:
    with pytest.raises(UnreadableImage):
        await PillowImageProcessor().webp_variants(jpeg(800, 400)[:300], (400,))
