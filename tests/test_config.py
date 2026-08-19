from datetime import timedelta

import pytest
from pydantic import ValidationError

from detectionsampler.config import DetectionSelectorConfig


def test_yaml_shaped_config_parses_into_nested_models():
    config = DetectionSelectorConfig(
        filters=[
            {
                'name': 'many_uncertain_persons',
                'match_detection': {'class_id_in': [0], 'confidence_below': 0.5, 'width_below': 0.001, 'height_below': 0.001},
                'matching_count_above': 3,
                'cooldown': '5s',
            },
            {'name': 'crowded', 'matching_count_above': 20},
        ],
        heartbeat_interval='1 day',
    )

    assert config.heartbeat_interval == timedelta(days=1)

    first, second = config.filters
    assert first.match_detection.class_id_in == [0]
    assert first.match_detection.confidence_below == 0.5
    assert first.matching_count_above == 3
    assert first.cooldown == timedelta(seconds=5)

    assert second.match_detection is None
    assert second.cooldown is None


def test_natural_durations_are_accepted():
    assert DetectionSelectorConfig(heartbeat_interval='1 day').heartbeat_interval == timedelta(days=1)


def test_unparseable_duration_is_rejected():
    '''The duration parser raises a ValueError, which has to surface as a config validation error.'''
    with pytest.raises(ValidationError):
        DetectionSelectorConfig(heartbeat_interval='not-a-duration')


def test_config_without_filters_and_heartbeat_is_rejected():
    '''Nothing would ever be forwarded - this also catches a settings file from before 1.0.0.'''
    with pytest.raises(ValidationError):
        DetectionSelectorConfig(filters=[])


def test_duplicate_filter_names_are_rejected():
    with pytest.raises(ValidationError):
        DetectionSelectorConfig(filters=[{'name': 'dupe'}, {'name': 'dupe'}])


def test_empty_class_id_in_is_rejected():
    '''An empty list would match nothing, which is never what a user means.'''
    with pytest.raises(ValidationError):
        DetectionSelectorConfig(filters=[{'name': 'nothing', 'match_detection': {'class_id_in': []}}])


def test_filters_only_config_is_valid():
    config = DetectionSelectorConfig(filters=[{'name': 'anything'}])

    assert config.heartbeat_interval is None
