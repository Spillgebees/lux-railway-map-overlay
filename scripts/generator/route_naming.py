from __future__ import annotations

import re
import unicodedata


def normalize_text(value: str) -> str:
    """Normalize names for fuzzy comparisons across multilingual OSM inputs."""
    normalized_value = unicodedata.normalize("NFKD", value.casefold())
    ascii_like_value = "".join(
        character
        for character in normalized_value
        if not unicodedata.combining(character)
    )
    cleaned_value = re.sub(r"[^a-z0-9]+", " ", ascii_like_value)
    return " ".join(cleaned_value.split())


def parse_other_tags(raw_other_tags: str) -> dict[str, str]:
    if not raw_other_tags:
        return {}

    return {
        key.replace(r"\"", '"')
        .replace(r"\\", "\\"): value.replace(r"\"", '"')
        .replace(r"\\", "\\")
        for key, value in re.findall(
            r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"', raw_other_tags
        )
    }


def iter_station_aliases(feature: dict) -> list[str]:
    """Collect station names from primary fields and selected name-like tags."""
    properties = feature.get("properties", {})
    aliases: list[str] = []

    for key in ("name", "uic_name"):
        value = properties.get(key, "")
        if value:
            aliases.append(value)

    other_tags = parse_other_tags(properties.get("other_tags", ""))
    for key, value in other_tags.items():
        if not value:
            continue
        if key in {
            "alt_name",
            "official_name",
            "ref_name",
            "SNCF:stop_name",
        } or key.startswith("name:"):
            aliases.extend(part.strip() for part in value.split(";") if part.strip())

    deduplicated_aliases: list[str] = []
    seen_aliases: set[str] = set()
    for alias in aliases:
        normalized_alias = normalize_text(alias)
        if not normalized_alias or normalized_alias in seen_aliases:
            continue
        seen_aliases.add(normalized_alias)
        deduplicated_aliases.append(alias)

    return deduplicated_aliases


def parse_name_endpoints(name: str, ref: str) -> tuple[str, str]:
    """Extract terminal station names from relation names like "RE 1: A - B"."""
    if not name.strip():
        return "", ""

    trimmed_name = name.strip()
    normalized_ref = normalize_text(ref)
    normalized_trimmed_name = normalize_text(trimmed_name)
    compact_normalized_ref = normalized_ref.replace(" ", "")
    compact_normalized_trimmed_name = normalized_trimmed_name.replace(" ", "")
    if compact_normalized_ref and compact_normalized_trimmed_name.startswith(
        compact_normalized_ref
    ):
        ref_pattern = r"\s*".join(re.escape(part) for part in ref.split())
        prefix_match = re.match(
            rf"^\s*{ref_pattern}\s*[:\-_>|<=]*\s*",
            trimmed_name,
            re.IGNORECASE,
        )
        if prefix_match is not None:
            trimmed_name = trimmed_name[prefix_match.end() :]

    if any(token in trimmed_name for token in ("=>", "->", "→")):
        parts = [
            part.strip()
            for part in re.split(r"\s*(?:=>|->|→)\s*", trimmed_name)
            if part.strip()
        ]
    elif " -- " in trimmed_name:
        parts = [part.strip() for part in trimmed_name.split(" -- ") if part.strip()]
    elif " - " in trimmed_name:
        parts = [part.strip() for part in trimmed_name.split(" - ") if part.strip()]
    else:
        parts = [trimmed_name]

    if len(parts) < 2:
        return "", ""

    return parts[0].strip(" :,"), parts[-1].strip(" :,")


def endpoints_match(left: str, right: str) -> bool:
    normalized_left = normalize_text(left)
    normalized_right = normalize_text(right)
    if not normalized_left or not normalized_right:
        return False
    return (
        normalized_left == normalized_right
        or normalized_left in normalized_right
        or normalized_right in normalized_left
    )


def resolve_endpoints(
    name: str, ref: str, endpoint_from: str, endpoint_to: str
) -> tuple[str, str]:
    """Prefer explicit from/to tags, but repair them from the relation name when the
    tags are missing, noisy, or collapse to the same normalized endpoint.
    """
    parsed_from, parsed_to = parse_name_endpoints(name, ref)

    effective_from = endpoint_from
    effective_to = endpoint_to

    if parsed_from and (
        not effective_from or not endpoints_match(effective_from, parsed_from)
    ):
        effective_from = parsed_from
    if parsed_to and (not effective_to or not endpoints_match(effective_to, parsed_to)):
        effective_to = parsed_to

    if (
        parsed_from
        and parsed_to
        and effective_from
        and effective_to
        and endpoints_match(effective_from, effective_to)
        and not endpoints_match(parsed_from, parsed_to)
    ):
        effective_from = parsed_from
        effective_to = parsed_to

    return effective_from.strip(), effective_to.strip()


def build_variant_signature(
    name: str, ref: str, endpoint_from: str, endpoint_to: str
) -> str:
    """Derive the non-endpoint part of a route name so branch variants deduplicate
    separately from the core service endpoints.
    """
    normalized_name = normalize_text(name)
    if not normalized_name:
        return ""

    normalized_ref = normalize_text(ref)
    if normalized_ref and normalized_name.startswith(normalized_ref):
        normalized_name = normalized_name[len(normalized_ref) :].lstrip(" :-_>|<=")

    endpoint_names = {
        normalized
        for normalized in (normalize_text(endpoint_from), normalize_text(endpoint_to))
        if normalized
    }

    parts = [
        part.strip()
        for part in re.split(r"\s*(?:--|->|=>|→)\s*|\s+[–—-]\s+", normalized_name)
        if part.strip()
    ]

    variant_parts: list[str] = []
    for part in parts:
        cleaned_part = part
        is_endpoint_like = False
        for endpoint_name in endpoint_names:
            if part == endpoint_name or part in endpoint_name or endpoint_name in part:
                cleaned_part = cleaned_part.replace(endpoint_name, " ").strip()
                if not cleaned_part or cleaned_part in {":", ","}:
                    is_endpoint_like = True
                continue

            if endpoint_name in cleaned_part:
                cleaned_part = cleaned_part.replace(endpoint_name, " ").strip()

        if is_endpoint_like:
            continue

        cleaned_part = cleaned_part.strip(" :,")
        if cleaned_part:
            variant_parts.append(cleaned_part)

    if variant_parts:
        return " | ".join(sorted(variant_parts))

    normalized_name = re.sub(r"[-=<>]+", " ", normalized_name)
    for endpoint_name in sorted(endpoint_names, key=len, reverse=True):
        normalized_name = normalized_name.replace(endpoint_name, " ")

    return " ".join(normalized_name.split()).strip(" :,")
