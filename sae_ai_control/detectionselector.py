import logging
from typing import Any

from prometheus_client import Counter, Histogram, Summary
from visionapi.sae_pb2 import SaeMessage
from datetime import datetime, timedelta
from .config import DetectionSelectorConfig

logging.basicConfig(format='%(asctime)s %(name)-15s %(levelname)-8s %(processName)-10s %(message)s')
logger = logging.getLogger(__name__)

GET_DURATION = Histogram('detection_selector_get_duration', 'The time it takes to deserialize the proto until returning the tranformed result as a serialized proto',
                         buckets=(0.0025, 0.005, 0.0075, 0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25))
OBJECT_COUNTER = Counter('detection_selector_object_counter', 'How many detections have been transformed')
PROTO_SERIALIZATION_DURATION = Summary('detection_selector_proto_serialization_duration', 'The time it takes to create a serialized output proto')
PROTO_DESERIALIZATION_DURATION = Summary('detection_selector_proto_deserialization_duration', 'The time it takes to deserialize an input proto')



class DetectionSelector:
    timedelta_timestamp = datetime.now()
    last_send_time = datetime.now()

    def __init__(self, config: DetectionSelectorConfig) -> None:
        self.config = config
        self.timedelta_timestamp = self._timedelta(config.time_past)
        self.last_selected_timestamp_ms = None
        logger.setLevel(self.config.log_level.value)

    def __call__(self, input_proto) -> Any:
        return self.get(input_proto)
    
    @GET_DURATION.time()
    def get(self, input_proto):
        sae_msg = self._unpack_proto(input_proto)

        # Your implementation goes (mostly) here
        logger.debug('Received SAE message from pipeline')
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
        send_msg: bool = False
        if (sae_msg.detections is not None and len(sae_msg.detections) > 0):
            for detection in sae_msg.detections:
                if detection.confidence < self.config.min_confidence:
                    send_msg = True
                    break
                width = detection.bounding_box.max_x - detection.bounding_box.min_x
                height = detection.bounding_box.max_y - detection.bounding_box.min_y
                if width < self.config.min_width:
                    send_msg = True
                    break
                if height < self.config.min_height:
                    send_msg = True
                    break
            if (sae_msg.detections is not None and len(sae_msg.detections) > self.config.max_detections):
                send_msg = True
            if self._is_time_past():
                send_msg = True
        if not send_msg:
            return None

        timestamp_ms = sae_msg.frame.timestamp_utc_ms
        # Suppressed frames do not restart the cooldown; measure from the last forwarded candidate.
        if (self.config.cooldown_seconds is not None
                and self.last_selected_timestamp_ms is not None
                and timestamp_ms - self.last_selected_timestamp_ms < self.config.cooldown_seconds * 1000):
            return None

        self.last_selected_timestamp_ms = timestamp_ms
        return sae_msg

    def _is_time_past(self) -> bool:
        if self.timedelta_timestamp is not None:
            current_time = datetime.now()
            if current_time - self.last_send_time >= self.timedelta_timestamp:
                self.last_send_time = current_time
                return True
            else:
                return False
    
    def _timedelta(self, period_str):
        if period_str.endswith('d'):
            value = int(period_str[:-1])
            return timedelta(days=value)
        elif period_str.endswith('s'):
            value = int(period_str[:-1])
            return timedelta(seconds=value)
        elif period_str.endswith('h'):
            value = int(period_str[:-1])
            return timedelta(hours=value)
        elif period_str.endswith('m'):
            value = int(period_str[:-1])
            return timedelta(minutes=value)
        # Add more cases as needed (e.g., 'h' for hours, 'm' for minutes)
        else:
            raise ValueError("Unsupported period format")
