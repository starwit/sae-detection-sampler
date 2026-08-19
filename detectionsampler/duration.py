import re
from datetime import timedelta

UNITS = {
    's': 1, 'sec': 1, 'second': 1, 'seconds': 1,
    'm': 60, 'min': 60, 'minute': 60, 'minutes': 60,
    'h': 3600, 'hr': 3600, 'hour': 3600, 'hours': 3600,
    'd': 86400, 'day': 86400, 'days': 86400,
    'w': 604800, 'week': 604800, 'weeks': 604800,
}
PATTERN = re.compile(r'(\d+(?:\.\d+)?)\s*([a-zA-Z]+)')


def parse_timedelta(value: str) -> timedelta:
    '''Parse a natural duration like `30s`, `10 minutes`, `2h30m`, `1 day`, `1 day, 30 seconds`.'''
    matches = PATTERN.findall(value)
    leftover = PATTERN.sub('', value).strip(' ,')
    if not matches or leftover:
        raise ValueError(f'Unparseable duration: {value!r}')

    total = 0.0
    for number, unit in matches:
        if unit.lower() not in UNITS:
            raise ValueError(f'Unknown duration unit {unit!r} in {value!r}, expected one of {", ".join(UNITS)}')
        total += float(number) * UNITS[unit.lower()]

    return timedelta(seconds=total)
