import pytest
from unittest.mock import MagicMock
from sae_ai_control.detectionselector import DetectionSelector, DetectionSelectorConfig

class DummyDetection:
    def __init__(self, confidence, min_x, max_x, min_y, max_y):
        self.confidence = confidence
        self.bounding_box = MagicMock()
        self.bounding_box.min_x = min_x
        self.bounding_box.max_x = max_x
        self.bounding_box.min_y = min_y
        self.bounding_box.max_y = max_y


@pytest.fixture
def config():
    cfg = DetectionSelectorConfig()
    cfg.min_confidence = 0.5
    cfg.min_width = 10
    cfg.min_height = 10
    cfg.max_detections = 4
    cfg.time_past = "1d"
    return cfg


@pytest.fixture
def selector(config):
    sel = DetectionSelector(config)
    # Patch _is_time_past to control its output
    sel._is_time_past = MagicMock(return_value=False)
    return sel

def make_msg(detections, timestamp=1_000):
    msg = MagicMock()
    msg.detections = detections
    msg.frame.timestamp_utc_ms = timestamp
    return msg

def test_filter_message_confidence_below_min(selector):
    detection = DummyDetection(confidence=0.4, min_x=0, max_x=20, min_y=0, max_y=20)
    msg = make_msg([detection])
    result = selector._filter_message(msg)
    assert result == msg
    
    detection = DummyDetection(confidence=0.6, min_x=0, max_x=20, min_y=0, max_y=20)
    msg = make_msg([detection])
    result = selector._filter_message(msg)
    assert result is None

def test_filter_message_width_below_min(selector):
    detection = DummyDetection(confidence=0.6, min_x=0, max_x=9, min_y=0, max_y=20)
    msg = make_msg([detection])
    result = selector._filter_message(msg)
    assert result == msg
    
    detection = DummyDetection(confidence=0.6, min_x=0, max_x=10, min_y=0, max_y=20)
    msg = make_msg([detection])
    result = selector._filter_message(msg)
    assert result is None

def test_filter_message_height_below_min(selector):
    detection = DummyDetection(confidence=0.6, min_x=0, max_x=20, min_y=0, max_y=9)
    msg = make_msg([detection])
    result = selector._filter_message(msg)
    assert result == msg 
        
    detection = DummyDetection(confidence=0.6, min_x=0, max_x=20, min_y=0, max_y=10)
    msg = make_msg([detection])
    result = selector._filter_message(msg)
    assert result is None


def test_filter_message_too_many_detections(selector):
    detections = [DummyDetection(0.6, 0, 20, 0, 20) for _ in range(5)]
    msg = make_msg(detections)
    result = selector._filter_message(msg)
    assert result == msg
    detections = [DummyDetection(0.6, 0, 20, 0, 20) for _ in range(4)]
    msg = make_msg(detections)
    result = selector._filter_message(msg)
    assert result is None
    
def test_filter_message_none_triggers(selector):
    msg = make_msg([])
    result = selector._filter_message(msg)
    assert result is None

def test_filter_message_all_ok(selector):
    detection = DummyDetection(confidence=0.6, min_x=0, max_x=20, min_y=0, max_y=20)
    msg = make_msg([detection])
    result = selector._filter_message(msg)
    assert result is None

def test_filter_message_applies_cooldown(config):
    config.cooldown_seconds = 10
    selector = DetectionSelector(config)
    selector._is_time_past = MagicMock(return_value=False)
    detection = DummyDetection(confidence=0.4, min_x=0, max_x=20, min_y=0, max_y=20)

    first = make_msg([detection], timestamp=1_000)
    during_cooldown = make_msg([detection], timestamp=10_999)
    after_cooldown = make_msg([detection], timestamp=11_000)

    assert selector._filter_message(first) == first
    assert selector._filter_message(during_cooldown) is None
    # The rejected frame did not restart the cooldown, so the boundary passes.
    assert selector._filter_message(after_cooldown) == after_cooldown
