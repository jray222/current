import io
from PIL import Image
from app.services.images import process_and_save_image, get_image_absolute_path, delete_image


def _generate_test_image_bytes(width=800, height=600, color="blue", format="PNG"):
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


def test_process_and_save_image_resizes():
    raw_bytes = _generate_test_image_bytes(width=1200, height=800)
    rel_path = process_and_save_image(raw_bytes, household_id=99)
    assert rel_path is not None
    assert rel_path.startswith("99/")
    assert rel_path.endswith(".jpg")

    abs_path = get_image_absolute_path(rel_path)
    assert abs_path is not None
    assert abs_path.is_file()

    # Verify resized dimensions
    with Image.open(abs_path) as saved_img:
        assert saved_img.format == "JPEG"
        assert saved_img.width <= 720
        assert saved_img.height <= 720

    # Cleanup
    delete_image(rel_path)
    assert not abs_path.is_file()


def test_directory_traversal_protection():
    # Attempt directory traversal
    traversal_path = "../../../etc/passwd"
    resolved = get_image_absolute_path(traversal_path)
    assert resolved is None

    null_path = get_image_absolute_path("")
    assert null_path is None
