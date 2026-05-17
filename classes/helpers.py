from datetime import datetime


def parse_date(date_str):
    """Parse various date formats into a Python date object for MySQL."""
    if not date_str or date_str.strip() == '':
        return None
    date_str = date_str.strip()
    for fmt in ('%m/%d/%Y', '%m/%d/%y'):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def parse_int(val):
    """Safely parse an integer, return None if empty or invalid."""
    try:
        return int(val.strip()) if val and val.strip() else None
    except (ValueError, AttributeError):
        return None