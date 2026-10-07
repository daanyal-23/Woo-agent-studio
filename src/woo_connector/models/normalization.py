"""Text and PII normalization utilities for WooCommerce domain models."""

import html
import re


def strip_html(raw_html: str | None) -> str:
    """Safely strip HTML tags and decode HTML entities from text."""
    if not raw_html:
        return ""
    # Strip HTML tags
    cleaned = re.sub(r"<[^>]+>", " ", raw_html)
    # Decode HTML entities (e.g. &amp;, &quot;)
    return html.unescape(cleaned)


def normalize_whitespace(text: str | None) -> str:
    """Collapse consecutive whitespace characters and trim edges."""
    if not text:
        return ""
    return " ".join(text.split()).strip()


def truncate_text(text: str | None, max_length: int = 500) -> str:
    """Enforce an upper bound on free-text length without failing."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip()


def clean_text(text: str | None, max_length: int = 500) -> str:
    """Pipeline: strip HTML, normalize whitespace, and enforce max length."""
    return truncate_text(normalize_whitespace(strip_html(text)), max_length=max_length)


def mask_email(email: str | None) -> str | None:
    """Mask email address for PII minimization (e.g. 'j***e@example.com').

    Preserves domain for diagnostic context while masking the local identifier.
    """
    if not email or not isinstance(email, str):
        return None

    cleaned = email.strip()
    if "@" not in cleaned:
        # Non-standard or malformed email: mask completely except first character
        if len(cleaned) <= 1:
            return "*"
        return cleaned[0] + "***"

    local_part, domain = cleaned.split("@", 1)
    if not local_part:
        return f"***@{domain}"

    if len(local_part) == 1:
        masked_local = f"{local_part}*"
    elif len(local_part) == 2:
        masked_local = f"{local_part[0]}*"
    else:
        masked_local = f"{local_part[0]}***{local_part[-1]}"

    return f"{masked_local}@{domain}"
