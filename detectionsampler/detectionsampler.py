import logging
from typing import Any, Dict, List, Optional

from prometheus_client import Counter, Histogram, Summary
from visionapi.sae_pb2 import Detection, SaeMessage

from .config import DetectionPredicatesConfig, DetectionSamplerConfig, FilterConfig

logging.basicConfig(format='%(asctime)s %(name)-15s %(levelname)-8s %(processName)-10s %(message)s')
logger = logging.getLogger(__name__)

GET_DURATION = Histogram('detection_sampler_get_duration', 'The time it takes to deserialize the proto until returning the tranformed result as a serialized proto',
                         buckets=(0.0025, 0.005, 0.0075, 0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25))
OBJECT_COUNTER = Counter('detection_sampler_object_counter', 'How many detections have been forwarded')
FILTER_MATCH_COUNTER = Counter('detection_sampler_filter_match_counter', 'How often a filter caused a message to be forwarded', labelnames=('filter',))
PROTO_SERIALIZATION_DURATION = Summary('detection_sampler_proto_serialization_duration', 'The time it takes to create a serialized output proto')
PROTO_DESERIALIZATION_DURATION = Summary('detection_sampler_proto_deserialization_duration', 'The time it takes to deserialize an input proto')

HEARTBEAT_LABEL = 'heartbeat'


class DetectionSampler:

    def __init__(self, config: DetectionSamplerConfig) -> None:
        self.config = config
        logger.setLevel(self.config.log_level.value)

        self._heartbeat_interval_ms = self._to_millis(config.heartbeat_interval)
        self._cooldown_ms: Dict[str, Optional[int]] = {f.name: self._to_millis(f.cooldown) for f in config.filters}

        # Timestamp of the last forwarded message (heartbeat baseline) and per filter the timestamp
        # of the last message that filter caused to be forwarded. Both in frame time.
        self._last_forward_ms: Optional[int] = None
        self._last_filter_forward_ms: Dict[str, int] = {}

        # Initialize all label values, so every configured filter shows up in the metrics
        FILTER_MATCH_COUNTER.labels(filter=HEARTBEAT_LABEL)
        for filter_config in config.filters:
            FILTER_MATCH_COUNTER.labels(filter=filter_config.name)

    def __call__(self, input_proto) -> Any:
        return self.get(input_proto)

    @GET_DURATION.time()
    def get(self, input_proto):
        sae_msg = self._unpack_proto(input_proto)

        sae_msg = self._filter_message(sae_msg)
        if sae_msg is None:
            return None
        else:
            return self._pack_proto(sae_msg)

    @PROTO_DESERIALIZATION_DURATION.time()
    def _unpack_proto(self, sae_message_bytes):
        sae_msg = SaeMessage()
        sae_msg.ParseFromString(sae_message_bytes)

        return sae_msg

    @PROTO_SERIALIZATION_DURATION.time()
    def _pack_proto(self, sae_msg: SaeMessage):
        return sae_msg.SerializeToString()

    def _filter_message(self, sae_msg: SaeMessage):
        '''Forward the message if any filter matches (OR) or the heartbeat interval has elapsed.'''
        timestamp_ms = sae_msg.frame.timestamp_utc_ms

        if self._last_forward_ms is None:
            # Take the first message as the heartbeat baseline, so it does not fire right away
            self._last_forward_ms = timestamp_ms

        matched = [f for f in self.config.filters if self._filter_matches(f, sae_msg)]
        ready = [f for f in matched if self._cooldown_elapsed(f, timestamp_ms)]

        if ready:
            for filter_config in ready:
                self._last_filter_forward_ms[filter_config.name] = timestamp_ms
                FILTER_MATCH_COUNTER.labels(filter=filter_config.name).inc()
            logger.debug(f'Forwarding message ({", ".join(f.name for f in ready)})')
        elif self._heartbeat_due(timestamp_ms):
            FILTER_MATCH_COUNTER.labels(filter=HEARTBEAT_LABEL).inc()
            logger.debug(f'Forwarding message ({HEARTBEAT_LABEL})')
        else:
            return None

        self._last_forward_ms = timestamp_ms
        OBJECT_COUNTER.inc(len(sae_msg.detections))

        return sae_msg

    def _filter_matches(self, filter_config: FilterConfig, sae_msg: SaeMessage) -> bool:
        return self._count_matching(filter_config, sae_msg.detections) > filter_config.matching_count_above

    def _count_matching(self, filter_config: FilterConfig, detections: List[Detection]) -> int:
        count = 0
        for detection in detections:
            if self._detection_matches(filter_config.match_detection, detection):
                count += 1
                if count > filter_config.matching_count_above:
                    break

        return count

    def _detection_matches(self, predicates: Optional[DetectionPredicatesConfig], detection: Detection) -> bool:
        '''All predicates that are set have to hold for this single detection.'''
        if predicates is None:
            return True

        if predicates.class_id_in is not None and detection.class_id not in predicates.class_id_in:
            return False
        if predicates.confidence_below is not None and detection.confidence >= predicates.confidence_below:
            return False

        bounding_box = detection.bounding_box
        if predicates.width_below is not None and bounding_box.max_x - bounding_box.min_x >= predicates.width_below:
            return False
        if predicates.height_below is not None and bounding_box.max_y - bounding_box.min_y >= predicates.height_below:
            return False

        return True

    def _cooldown_elapsed(self, filter_config: FilterConfig, timestamp_ms: int) -> bool:
        '''Suppressed frames do not restart the cooldown; measure from the last forwarded candidate.'''
        cooldown_ms = self._cooldown_ms[filter_config.name]
        last_forward_ms = self._last_filter_forward_ms.get(filter_config.name)
        if cooldown_ms is None or last_forward_ms is None:
            return True

        return timestamp_ms - last_forward_ms >= cooldown_ms

    def _heartbeat_due(self, timestamp_ms: int) -> bool:
        if self._heartbeat_interval_ms is None:
            return False

        return timestamp_ms - self._last_forward_ms >= self._heartbeat_interval_ms

    @staticmethod
    def _to_millis(interval) -> Optional[int]:
        return None if interval is None else int(interval.total_seconds() * 1000)
