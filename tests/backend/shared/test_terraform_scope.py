import pytest

from backend.shared.terraform_scope import MAX_DISPLAY_NAME, display_name


@pytest.mark.parametrize(("first", "second"), [
    ("customer_records_archive_primary_region_a", "customer_records_archive_primary_region_b"),
    ("long_module_" + "x" * 40 + "a/resource", "long_module_" + "x" * 40 + "b/resource"),
    ("a.b", "ab"),
])
def test_display_names_preserve_distinct_resource_identity(first, second):
    assert display_name(first) != display_name(second)
    assert display_name(first) == display_name(first)
    assert all(len(segment) <= MAX_DISPLAY_NAME for segment in display_name(first).split("/"))


def test_short_safe_display_names_are_unchanged():
    assert display_name("modules/app/data") == "modules/app/data"
