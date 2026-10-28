from PIL import Image
from app import apply_adjustments


def values(**overrides):
    result = {"exposure": 0, "brightness": 0, "contrast": 0, "saturation": 0,
              "sharpness": 0, "warmth": 0, "vignette": 0}
    result.update(overrides)
    return result


def test_zero_adjustments_preserve_pixels():
    image = Image.new("RGB", (8, 8), (120, 140, 160))
    result = apply_adjustments(image, values())
    assert result.size == image.size
    assert list(result.getdata()) == list(image.getdata())


def test_adjustments_keep_dimensions():
    image = Image.new("RGB", (20, 12), (100, 120, 140))
    result = apply_adjustments(image, values(exposure=20, brightness=5, contrast=10,
                                            saturation=-5, sharpness=15, warmth=10, vignette=20))
    assert result.size == image.size
    assert result.mode == "RGB"


def test_rotation_and_crop_are_supported_by_pillow():
    image = Image.new("RGB", (40, 20), (90, 100, 110))
    rotated = image.rotate(90, expand=True)
    cropped = rotated.crop((0, 0, 10, 15))
    assert rotated.size == (20, 40)
    assert cropped.size == (10, 15)
