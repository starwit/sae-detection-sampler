from datetime import timedelta
from typing import Any, List, Optional

from pydantic import BaseModel, BeforeValidator, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Annotated
from visionlib.pipeline.settings import LogLevel, YamlConfigSettingsSource

from .duration import parse_timedelta


def _parse_duration(value: Any) -> Any:
    return parse_timedelta(value) if isinstance(value, str) else value


NaturalTimedelta = Annotated[timedelta, BeforeValidator(_parse_duration)]


class RedisConfig(BaseModel):
    host: str = 'localhost'
    port: Annotated[int, Field(ge=1, le=65536)] = 6379
    stream_id: str = 'stream1'
    input_stream_prefix: str = 'objecttracker'
    output_stream_prefix: str = 'detectionsampler'


class DetectionPredicatesConfig(BaseModel):
    class_id_in: Optional[Annotated[List[int], Field(min_length=1)]] = None
    class_id_not_in: Optional[Annotated[List[int], Field(min_length=1)]] = None
    confidence_above: Optional[Annotated[float, Field(ge=0)]] = None
    confidence_below: Optional[Annotated[float, Field(gt=0)]] = None
    width_above: Optional[Annotated[float, Field(ge=0)]] = None
    width_below: Optional[Annotated[float, Field(gt=0)]] = None
    height_above: Optional[Annotated[float, Field(ge=0)]] = None
    height_below: Optional[Annotated[float, Field(gt=0)]] = None

    @model_validator(mode='after')
    def _validate_bounds(self):
        for subject in ('confidence', 'width', 'height'):
            above = getattr(self, f'{subject}_above')
            below = getattr(self, f'{subject}_below')
            if above is not None and below is not None and below <= above:
                raise ValueError(f'{subject}_below has to be greater than {subject}_above, no detection could match')

        return self


class FilterConfig(BaseModel):
    name: str
    match_detection: Optional[DetectionPredicatesConfig] = None
    matching_count_above: Optional[Annotated[int, Field(ge=0)]] = None
    matching_count_below: Optional[Annotated[int, Field(ge=1)]] = None
    cooldown: Optional[NaturalTimedelta] = None

    @model_validator(mode='after')
    def _validate_bounds(self):
        if (self.matching_count_above is not None and self.matching_count_below is not None
                and self.matching_count_below <= self.matching_count_above + 1):
            raise ValueError('matching_count_below has to be greater than matching_count_above + 1, no count could match')

        return self


class DetectionSamplerConfig(BaseSettings):
    log_level: LogLevel = LogLevel.WARNING
    redis: RedisConfig = RedisConfig()
    prometheus_port: Annotated[int, Field(ge=1024, le=65536)] = 8000

    filters: List[FilterConfig] = []
    heartbeat_interval: Optional[NaturalTimedelta] = None

    model_config = SettingsConfigDict(env_nested_delimiter='__')

    @model_validator(mode='after')
    def _validate_filters(self):
        if not self.filters and self.heartbeat_interval is None:
            raise ValueError('No filters and no heartbeat_interval configured, no message would ever be forwarded')

        names = [f.name for f in self.filters]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f'Filter names have to be unique, found duplicates: {", ".join(duplicates)}')

        return self

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
        return (init_settings, env_settings, YamlConfigSettingsSource(settings_cls), file_secret_settings)
