from datetime import timedelta

import pytest
from pydantic import ValidationError

from detectionsampler.config import DetectionSamplerConfig


def test_yaml_shaped_config_parses_into_nested_models():
    config = DetectionSamplerConfig(
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
    assert DetectionSamplerConfig(heartbeat_interval='1 day').heartbeat_interval == timedelta(days=1)


def test_unparseable_duration_is_rejected():
    '''The duration parser raises a ValueError, which has to surface as a config validation error.'''
    with pytest.raises(ValidationError):
        DetectionSamplerConfig(heartbeat_interval='not-a-duration')


def test_config_without_filters_and_heartbeat_is_rejected():
    '''Nothing would ever be forwarded - this also catches a settings file from before 1.0.0.'''
    with pytest.raises(ValidationError):
        DetectionSamplerConfig(filters=[])


def test_duplicate_filter_names_are_rejected():
    with pytest.raises(ValidationError):
        DetectionSamplerConfig(filters=[{'name': 'dupe'}, {'name': 'dupe'}])


def test_empty_class_id_in_is_rejected():
    '''An empty list would match nothing, which is never what a user means.'''
    with pytest.raises(ValidationError):
        DetectionSamplerConfig(filters=[{'name': 'nothing', 'match_detection': {'class_id_in': []}}])


@pytest.mark.parametrize('predicates', [
    {'confidence_above': 0.7, 'confidence_below': 0.3},
    {'confidence_above': 0.5, 'confidence_below': 0.5},
    {'width_above': 0.5, 'width_below': 0.1},
    {'height_above': 0.5, 'height_below': 0.1},
])
def test_inverted_predicate_bounds_are_rejected(predicates):
    '''No detection could ever fall into such a band, so it is a configuration mistake.'''
    with pytest.raises(ValidationError):
        DetectionSamplerConfig(filters=[{'name': 'impossible', 'match_detection': predicates}])


@pytest.mark.parametrize('bounds', [
    {'matching_count_above': 3, 'matching_count_below': 2},
    {'matching_count_above': 2, 'matching_count_below': 2},
    {'matching_count_above': 2, 'matching_count_below': 3},  # would require a count of both >2 and <3
])
def test_inverted_matching_count_bounds_are_rejected(bounds):
    with pytest.raises(ValidationError):
        DetectionSamplerConfig(filters=[{'name': 'impossible', **bounds}])


def test_filters_only_config_is_valid():
    config = DetectionSamplerConfig(filters=[{'name': 'anything'}])

    assert config.heartbeat_interval is None
