import pytest

from detectionsampler.config import DetectionSamplerConfig


# This is necessary to prevent tests from accidentally loading real config files
@pytest.fixture(autouse=True)
def set_settings_file_location(monkeypatch):
    monkeypatch.setenv('SETTINGS_FILE', '/tmp/should_not_exist.yaml')
    # Environment variables take precedence over the settings file, so they have to go as well
    for field_name in DetectionSamplerConfig.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)
