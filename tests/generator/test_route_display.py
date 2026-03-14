from __future__ import annotations

from generator.route_display import (
    assign_route_offset_slots,
    geometry_from_segments,
    normalize_hex_color,
    offset_segments_for_display,
    resolve_display_color,
    resolve_display_text_color,
)


def test_normalize_hex_color_uppercases_valid_values() -> None:
    assert normalize_hex_color(" #ff00aa ") == "#FF00AA"
    assert normalize_hex_color("red") == ""


def test_resolve_display_color_uses_fallback_when_colour_missing() -> None:
    assert resolve_display_color({"colour": "#00aa11"}) == "#00AA11"
    assert resolve_display_color({}) == "#5B6675"


def test_resolve_display_text_color_uses_dark_text_for_light_lines() -> None:
    assert resolve_display_text_color("#F8FAFC") == "#0F172A"
    assert resolve_display_text_color("#0F172A") == "#0F172A"


def test_geometry_from_segments_uses_line_string_for_single_segment() -> None:
    geometry = geometry_from_segments([[[6.0, 49.6], [6.1, 49.7]]])

    assert geometry == {
        "type": "LineString",
        "coordinates": [[6.0, 49.6], [6.1, 49.7]],
    }


def test_geometry_from_segments_uses_multi_line_string_for_multiple_segments() -> None:
    segments = [
        [[6.0, 49.0], [6.1, 49.1]],
        [[6.2, 49.2], [6.3, 49.3]],
    ]
    result = geometry_from_segments(segments)
    assert result["type"] == "MultiLineString"
    assert result["coordinates"] == segments


def test_assign_route_offset_slots_shares_slot_for_same_group_key() -> None:
    slots = assign_route_offset_slots(
        [{1, 2, 3}, {2, 3, 4}, {9, 10}],
        [("re1",), ("re1",), ("rb2",)],
    )

    assert slots[0] == slots[1]
    assert slots[2] in {-0.5, 0.0, 0.5}


def test_offset_segments_for_display_returns_unchanged_for_zero_slot():
    segments = [[[6.13, 49.6], [6.14, 49.6], [6.15, 49.6]]]
    result = offset_segments_for_display(segments, 0.0)
    assert result == segments


def test_offset_segments_for_display_shifts_geometry_for_nonzero_slot():
    segments = [[[6.13, 49.6], [6.14, 49.6], [6.15, 49.6]]]
    result = offset_segments_for_display(segments, 1.0)
    # result should differ from input (offset applied)
    assert result != segments
    # should still have at least one segment with at least 2 points
    assert len(result) >= 1
    assert all(len(seg) >= 2 for seg in result)


def test_offset_segments_for_display_handles_short_segment():
    # a segment too short to meaningfully offset should fall back gracefully
    segments = [[[6.13, 49.6], [6.130001, 49.6]]]
    result = offset_segments_for_display(segments, 1.0)
    assert len(result) >= 1


def test_offset_segments_for_display_preserves_multiple_segments():
    segments = [
        [[6.13, 49.6], [6.14, 49.6], [6.15, 49.6]],
        [[6.16, 49.6], [6.17, 49.6], [6.18, 49.6]],
    ]
    result = offset_segments_for_display(segments, 1.0)
    # should produce at least as many segments as input
    assert len(result) >= 2
