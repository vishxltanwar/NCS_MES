import re


def clean_scan_data(raw: str) -> str:
    """Normalize raw barcode scanner data before application use."""
    cleaned = raw.replace("\x00", "").replace("\r", "").replace("\n", "")
    cleaned = cleaned.strip()
    return re.sub(r" {2,}", " ", cleaned)
