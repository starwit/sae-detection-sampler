from unittest.mock import MagicMock

import pytest

from detectionsampler.config import (DetectionPredicatesConfig,
                                     DetectionSamplerConfig, FilterConfig)
from detectionsampler.detectionsampler import (DetectionSampler,
                                               detection_matches,
                                               filter_matches)

PERSON = 0
CAR = 1


class DummyDetection:
    # Bounding box coordinates are normalized to [0, 1], as they are on the wire
    def __init__(self, confidence=0.9, class_id=PERSON, min_x=0.1, max_x=0.5, min_y=0.1, max_y=0.5):
        self.confidence = confidence
        self.class_id = class_id
        self.bounding_box = MagicMock()
        self.bounding_box.min_x = min_x
        self.bounding_box.max_x = max_x
        self.bounding_box.min_y = min_y
        self.bounding_box.max_y = max_y


def make_msg(detections, timestamp=1_000):
    msg = MagicMock()
    msg.detections = detections
    msg.frame.timestamp_utc_ms = timestamp
    return msg


def make_sampler(*filters, heartbeat_interval=None):
    # Pass every value explicitly so settings.yaml / env vars cannot leak into the tests
    config = DetectionSamplerConfig(
        log_level='WARNING',
        filters=list(filters),
        heartbeat_interval=heartbeat_interval,
    )
    return DetectionSampler(config)


# --- detection predicates -----------------------------------------------------------------------

@pytest.mark.parametrize('predicates,detection,expected', [
    ({'class_id_in': [CAR, 7]}, DummyDetection(class_id=CAR), True),
    ({'class_id_in': [CAR, 7]}, DummyDetection(class_id=7), True),
    ({'class_id_in': [CAR, 7]}, DummyDetection(class_id=PERSON), False),
    ({'class_id_not_in': [CAR, 7]}, DummyDetection(class_id=PERSON), True),
    ({'class_id_not_in': [CAR, 7]}, DummyDetection(class_id=CAR), False),
    ({'confidence_below': 0.5}, DummyDetection(confidence=0.4), True),
    ({'confidence_below': 0.5}, DummyDetection(confidence=0.6), False),
    ({'confidence_above': 0.5}, DummyDetection(confidence=0.6), True),
    ({'confidence_above': 0.5}, DummyDetection(confidence=0.4), False),
    ({'width_below': 0.1}, DummyDetection(min_x=0.2, max_x=0.25), True),
    ({'width_below': 0.1}, DummyDetection(min_x=0.2, max_x=0.6), False),
    ({'width_above': 0.3}, DummyDetection(min_x=0.2, max_x=0.6), True),
    ({'width_above': 0.3}, DummyDetection(min_x=0.2, max_x=0.25), False),
    ({'height_below': 0.1}, DummyDetection(min_y=0.2, max_y=0.25), True),
    ({'height_below': 0.1}, DummyDetection(min_y=0.2, max_y=0.6), False),
    ({'height_above': 0.3}, DummyDetection(min_y=0.2, max_y=0.6), True),
    ({'height_above': 0.3}, DummyDetection(min_y=0.2, max_y=0.25), False),
])
def test_single_predicate(predicates, detection, expected):
    assert detection_matches(DetectionPredicatesConfig(**predicates), detection) is expected


@pytest.mark.parametrize('predicates,detection,expected', [
    # A band between two bounds of the same subject
    ({'confidence_above': 0.3, 'confidence_below': 0.7}, DummyDetection(confidence=0.5), True),
    ({'confidence_above': 0.3, 'confidence_below': 0.7}, DummyDetection(confidence=0.2), False),
    ({'confidence_above': 0.3, 'confidence_below': 0.7}, DummyDetection(confidence=0.8), False),
    # Predicates over different subjects are ANDed
    ({'class_id_in': [PERSON], 'confidence_below': 0.5}, DummyDetection(class_id=PERSON, confidence=0.4), True),
    ({'class_id_in': [PERSON], 'confidence_below': 0.5}, DummyDetection(class_id=PERSON, confidence=0.6), False),
    ({'class_id_in': [PERSON], 'confidence_below': 0.5}, DummyDetection(class_id=CAR, confidence=0.4), False),
])
def test_predicates_are_anded(predicates, detection, expected):
    assert detection_matches(DetectionPredicatesConfig(**predicates), detection) is expected


def test_unset_predicates_are_inactive():
    '''Only `width_below` is configured, so neither a low confidence nor a flat box may trigger it.'''
    predicates = DetectionPredicatesConfig(width_below=0.1)

    assert detection_matches(predicates, DummyDetection(confidence=0.01, min_x=0.0, max_x=0.5, min_y=0.0, max_y=0.01)) is False


def test_no_predicates_match_any_detection():
    assert detection_matches(None, DummyDetection()) is True
    assert detection_matches(DetectionPredicatesConfig(), DummyDetection()) is True


# --- matching count -----------------------------------------------------------------------------

@pytest.mark.parametrize('bounds,matching_detections,expected', [
    # Without bounds a single matching detection is enough
    ({}, 0, False),
    ({}, 1, True),
    ({'matching_count_above': 2}, 2, False),
    ({'matching_count_above': 2}, 3, True),
    ({'matching_count_below': 1}, 0, True),
    ({'matching_count_below': 1}, 1, False),
    ({'matching_count_below': 3}, 2, True),
    ({'matching_count_below': 3}, 3, False),
    ({'matching_count_above': 1, 'matching_count_below': 4}, 1, False),
    ({'matching_count_above': 1, 'matching_count_below': 4}, 2, True),
    ({'matching_count_above': 1, 'matching_count_below': 4}, 3, True),
    ({'matching_count_above': 1, 'matching_count_below': 4}, 4, False),
])
def test_matching_count_bounds(bounds, matching_detections, expected):
    filter_config = FilterConfig(name='persons', match_detection={'class_id_in': [PERSON]}, **bounds)
    detections = [DummyDetection(class_id=PERSON) for _ in range(matching_detections)]

    assert filter_matches(filter_config, detections) is expected


def test_only_matching_detections_are_counted():
    filter_config = FilterConfig(name='many_persons', match_detection={'class_id_in': [PERSON]}, matching_count_above=2)

    persons_and_cars = [DummyDetection(class_id=PERSON) for _ in range(2)] + [DummyDetection(class_id=CAR) for _ in range(5)]
    assert filter_matches(filter_config, persons_and_cars) is False

    assert filter_matches(filter_config, [DummyDetection(class_id=PERSON) for _ in range(3)]) is True


def test_count_without_predicates_counts_all_detections():
    filter_config = FilterConfig(name='crowded', matching_count_above=2)

    assert filter_matches(filter_config, [DummyDetection(class_id=CAR) for _ in range(2)]) is False
    assert filter_matches(filter_config, [DummyDetection(class_id=CAR) for _ in range(3)]) is True


# --- module level -------------------------------------------------------------------------------

def test_predicates_are_anded_per_detection():
    '''One and the same detection has to satisfy all predicates, not the frame as a whole.'''
    sampler = make_sampler({'name': 'low_conf_persons', 'match_detection': {'class_id_in': [PERSON], 'confidence_below': 0.4}})

    # A person and a low confidence detection, but not in the same detection
    mixed = make_msg([DummyDetection(confidence=0.9, class_id=PERSON), DummyDetection(confidence=0.2, class_id=CAR)])
    assert sampler._filter_message(mixed) is None

    low_conf_person = make_msg([DummyDetection(confidence=0.3, class_id=PERSON)])
    assert sampler._filter_message(low_conf_person) == low_conf_person


def test_filters_are_ored():
    sampler = make_sampler(
        {'name': 'low_confidence', 'match_detection': {'confidence_below': 0.5}},
        {'name': 'cars', 'match_detection': {'class_id_in': [CAR]}},
    )

    by_first = make_msg([DummyDetection(confidence=0.4, class_id=PERSON)])
    assert sampler._filter_message(by_first) == by_first

    by_second = make_msg([DummyDetection(confidence=0.9, class_id=CAR)])
    assert sampler._filter_message(by_second) == by_second

    by_neither = make_msg([DummyDetection(confidence=0.9, class_id=PERSON)])
    assert sampler._filter_message(by_neither) is None


def test_cooldown_suppresses_the_same_filter():
    sampler = make_sampler({'name': 'low_confidence', 'match_detection': {'confidence_below': 0.5}, 'cooldown': '10s'})
    detection = DummyDetection(confidence=0.4)

    first = make_msg([detection], timestamp=1_000)
    during_cooldown = make_msg([detection], timestamp=10_999)
    after_cooldown = make_msg([detection], timestamp=11_000)

    assert sampler._filter_message(first) == first
    assert sampler._filter_message(during_cooldown) is None
    # The rejected frame did not restart the cooldown, so the boundary passes.
    assert sampler._filter_message(after_cooldown) == after_cooldown


def test_cooldown_of_a_suppressed_filter_is_not_restarted_by_another_filter():
    sampler = make_sampler(
        {'name': 'cars', 'match_detection': {'class_id_in': [CAR]}, 'cooldown': '10s'},
        {'name': 'persons', 'match_detection': {'class_id_in': [PERSON]}},
    )
    car = DummyDetection(class_id=CAR)
    person = DummyDetection(class_id=PERSON)

    assert sampler._filter_message(make_msg([car], timestamp=1_000)) is not None

    # Forwarded by 'persons' while 'cars' is still in cooldown
    both = make_msg([car, person], timestamp=5_000)
    assert sampler._filter_message(both) == both

    # 'cars' is measured from its own last forward at 1_000, not from the one at 5_000
    assert sampler._filter_message(make_msg([car], timestamp=11_000)) is not None


def test_heartbeat_fires_without_any_detections():
    sampler = make_sampler({'name': 'cars', 'match_detection': {'class_id_in': [CAR]}}, heartbeat_interval='10s')

    # The first message is the heartbeat baseline
    assert sampler._filter_message(make_msg([], timestamp=1_000)) is None
    assert sampler._filter_message(make_msg([], timestamp=10_999)) is None

    heartbeat = make_msg([], timestamp=11_000)
    assert sampler._filter_message(heartbeat) == heartbeat


def test_heartbeat_is_reset_by_a_forwarded_message():
    sampler = make_sampler({'name': 'cars', 'match_detection': {'class_id_in': [CAR]}}, heartbeat_interval='10s')
    car = DummyDetection(class_id=CAR)

    assert sampler._filter_message(make_msg([], timestamp=1_000)) is None

    by_filter = make_msg([car], timestamp=6_000)
    assert sampler._filter_message(by_filter) == by_filter

    # Heartbeat now measures from 6_000, not from 1_000
    assert sampler._filter_message(make_msg([], timestamp=15_000)) is None

    heartbeat = make_msg([], timestamp=16_000)
    assert sampler._filter_message(heartbeat) == heartbeat


def test_without_heartbeat_unmatched_messages_are_never_forwarded():
    sampler = make_sampler({'name': 'cars', 'match_detection': {'class_id_in': [CAR]}})

    for timestamp in (1_000, 10_000_000):
        assert sampler._filter_message(make_msg([DummyDetection(class_id=PERSON)], timestamp=timestamp)) is None
