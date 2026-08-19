from unittest.mock import MagicMock

import pytest

from detectionsampler.detectionselector import (DetectionSelector,
                                                DetectionSelectorConfig)

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


def make_selector(*filters, heartbeat_interval=None):
    # Pass every value explicitly so settings.yaml / env vars cannot leak into the tests
    config = DetectionSelectorConfig(
        log_level='WARNING',
        filters=list(filters),
        heartbeat_interval=heartbeat_interval,
    )
    return DetectionSelector(config)


def test_predicates_are_anded_per_detection():
    '''One and the same detection has to satisfy all predicates of a filter.'''
    selector = make_selector({'name': 'low_conf_persons', 'match_detection': {'class_id_in': [PERSON], 'confidence_below': 0.4}})

    # A person and a low confidence detection, but not in the same detection
    mixed = make_msg([DummyDetection(confidence=0.9, class_id=PERSON), DummyDetection(confidence=0.2, class_id=CAR)])
    assert selector._filter_message(mixed) is None

    low_conf_person = make_msg([DummyDetection(confidence=0.3, class_id=PERSON)])
    assert selector._filter_message(low_conf_person) == low_conf_person


def test_class_id_in_is_any_of():
    selector = make_selector({'name': 'vehicles', 'match_detection': {'class_id_in': [CAR, 7]}})

    for class_id in (CAR, 7):
        msg = make_msg([DummyDetection(class_id=class_id)])
        assert selector._filter_message(msg) == msg

    msg = make_msg([DummyDetection(class_id=PERSON)])
    assert selector._filter_message(msg) is None


def test_confidence_below():
    selector = make_selector({'name': 'low_confidence', 'match_detection': {'confidence_below': 0.5}})

    below = make_msg([DummyDetection(confidence=0.4)])
    assert selector._filter_message(below) == below

    above = make_msg([DummyDetection(confidence=0.6)])
    assert selector._filter_message(above) is None


def test_width_below():
    selector = make_selector({'name': 'narrow', 'match_detection': {'width_below': 0.1}})

    below = make_msg([DummyDetection(min_x=0.2, max_x=0.25)])
    assert selector._filter_message(below) == below

    above = make_msg([DummyDetection(min_x=0.2, max_x=0.6)])
    assert selector._filter_message(above) is None


def test_height_below():
    selector = make_selector({'name': 'flat', 'match_detection': {'height_below': 0.1}})

    below = make_msg([DummyDetection(min_y=0.2, max_y=0.25)])
    assert selector._filter_message(below) == below

    above = make_msg([DummyDetection(min_y=0.2, max_y=0.6)])
    assert selector._filter_message(above) is None


def test_unset_predicates_are_inactive():
    '''Only `width_below` is configured, so neither a low confidence nor a flat box may trigger it.'''
    selector = make_selector({'name': 'narrow', 'match_detection': {'width_below': 0.1}})

    msg = make_msg([DummyDetection(confidence=0.01, min_x=0.0, max_x=0.5, min_y=0.0, max_y=0.01)])
    assert selector._filter_message(msg) is None


def test_filter_without_detection_block_matches_any_detection():
    selector = make_selector({'name': 'anything'})

    msg = make_msg([DummyDetection()])
    assert selector._filter_message(msg) == msg

    assert selector._filter_message(make_msg([])) is None


def test_matching_count_above_counts_only_matching_detections():
    selector = make_selector({'name': 'many_persons', 'match_detection': {'class_id_in': [PERSON]}, 'matching_count_above': 2})

    two_persons = make_msg([DummyDetection(class_id=PERSON) for _ in range(2)] + [DummyDetection(class_id=CAR) for _ in range(5)])
    assert selector._filter_message(two_persons) is None

    three_persons = make_msg([DummyDetection(class_id=PERSON) for _ in range(3)])
    assert selector._filter_message(three_persons) == three_persons


def test_matching_count_above_without_predicates_counts_all_detections():
    selector = make_selector({'name': 'crowded', 'matching_count_above': 4})

    assert selector._filter_message(make_msg([DummyDetection() for _ in range(4)])) is None

    crowded = make_msg([DummyDetection() for _ in range(5)])
    assert selector._filter_message(crowded) == crowded


def test_filters_are_ored():
    selector = make_selector(
        {'name': 'low_confidence', 'match_detection': {'confidence_below': 0.5}},
        {'name': 'cars', 'match_detection': {'class_id_in': [CAR]}},
    )

    by_first = make_msg([DummyDetection(confidence=0.4, class_id=PERSON)])
    assert selector._filter_message(by_first) == by_first

    by_second = make_msg([DummyDetection(confidence=0.9, class_id=CAR)])
    assert selector._filter_message(by_second) == by_second

    by_neither = make_msg([DummyDetection(confidence=0.9, class_id=PERSON)])
    assert selector._filter_message(by_neither) is None


def test_cooldown_suppresses_the_same_filter():
    selector = make_selector({'name': 'low_confidence', 'match_detection': {'confidence_below': 0.5}, 'cooldown': '10s'})
    detection = DummyDetection(confidence=0.4)

    first = make_msg([detection], timestamp=1_000)
    during_cooldown = make_msg([detection], timestamp=10_999)
    after_cooldown = make_msg([detection], timestamp=11_000)

    assert selector._filter_message(first) == first
    assert selector._filter_message(during_cooldown) is None
    # The rejected frame did not restart the cooldown, so the boundary passes.
    assert selector._filter_message(after_cooldown) == after_cooldown


def test_cooldown_of_a_suppressed_filter_is_not_restarted_by_another_filter():
    selector = make_selector(
        {'name': 'cars', 'match_detection': {'class_id_in': [CAR]}, 'cooldown': '10s'},
        {'name': 'persons', 'match_detection': {'class_id_in': [PERSON]}},
    )
    car = DummyDetection(class_id=CAR)
    person = DummyDetection(class_id=PERSON)

    assert selector._filter_message(make_msg([car], timestamp=1_000)) is not None

    # Forwarded by 'persons' while 'cars' is still in cooldown
    both = make_msg([car, person], timestamp=5_000)
    assert selector._filter_message(both) == both

    # 'cars' is measured from its own last forward at 1_000, not from the one at 5_000
    assert selector._filter_message(make_msg([car], timestamp=11_000)) is not None


def test_heartbeat_fires_without_any_detections():
    selector = make_selector({'name': 'cars', 'match_detection': {'class_id_in': [CAR]}}, heartbeat_interval='10s')

    # The first message is the heartbeat baseline
    assert selector._filter_message(make_msg([], timestamp=1_000)) is None
    assert selector._filter_message(make_msg([], timestamp=10_999)) is None

    heartbeat = make_msg([], timestamp=11_000)
    assert selector._filter_message(heartbeat) == heartbeat


def test_heartbeat_is_reset_by_a_forwarded_message():
    selector = make_selector({'name': 'cars', 'match_detection': {'class_id_in': [CAR]}}, heartbeat_interval='10s')
    car = DummyDetection(class_id=CAR)

    assert selector._filter_message(make_msg([], timestamp=1_000)) is None

    by_filter = make_msg([car], timestamp=6_000)
    assert selector._filter_message(by_filter) == by_filter

    # Heartbeat now measures from 6_000, not from 1_000
    assert selector._filter_message(make_msg([], timestamp=15_000)) is None

    heartbeat = make_msg([], timestamp=16_000)
    assert selector._filter_message(heartbeat) == heartbeat


def test_no_heartbeat_configured_never_forwards_unmatched_messages():
    selector = make_selector({'name': 'cars', 'match_detection': {'class_id_in': [CAR]}})

    for timestamp in (1_000, 10_000_000):
        assert selector._filter_message(make_msg([DummyDetection(class_id=PERSON)], timestamp=timestamp)) is None
