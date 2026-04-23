import pytest

from paper_analyzer.config import get_settings
from paper_analyzer.services import worker


def test_validate_worker_count_accepts_valid_values():
    assert worker._validate_worker_count(1) == 1
    assert worker._validate_worker_count(3) == 3


def test_validate_worker_count_rejects_out_of_range():
    with pytest.raises(ValueError):
        worker._validate_worker_count(0)
    with pytest.raises(ValueError):
        worker._validate_worker_count(4)


def test_default_worker_concurrency_from_settings(test_env):
    settings = get_settings()
    assert settings.worker_concurrency == 3
