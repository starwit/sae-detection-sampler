from datetime import timedelta

import pytest

from detectionsampler.duration import parse_timedelta


@pytest.mark.parametrize('value,expected', [
    ('30s', timedelta(seconds=30)),
    ('1d', timedelta(days=1)),
    ('5h', timedelta(hours=5)),
    ('1w', timedelta(weeks=1)),
    ('10 minutes', timedelta(minutes=10)),
    ('2h30m', timedelta(hours=2, minutes=30)),
    ('1 day, 30 seconds', timedelta(days=1, seconds=30)),
    ('1.5h', timedelta(minutes=90)),
    ('1 HOUR', timedelta(hours=1)),
])
def test_parse_timedelta_accepts_natural_durations(value, expected):
    assert parse_timedelta(value) == expected


@pytest.mark.parametrize('value', [
    '',
    'not-a-duration',
    '5 apples',  # unknown unit
    '10',  # no unit
    '1d foo',  # trailing garbage
])
def test_parse_timedelta_rejects_garbage(value):
    '''Anything unparseable has to raise instead of silently becoming a zero duration.'''
    with pytest.raises(ValueError):
        parse_timedelta(value)
