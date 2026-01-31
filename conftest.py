# conftest.py
import os
import pytest

@pytest.fixture(autouse=True)
def set_env_vars():
    """Automatically set MS_CLIENT_ID for all tests."""
    os.environ['MS_CLIENT_ID'] = 'dummy_client_id_for_testing'
    yield
    # Cleanup (optional)
    os.environ.pop('MS_CLIENT_ID', None)

