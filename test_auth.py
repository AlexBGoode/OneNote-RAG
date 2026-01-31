# test_auth.py - FIXED VERSION
import pytest
import os
import sys
import tempfile
from unittest.mock import Mock, patch, mock_open, MagicMock
from pathlib import Path

# Add the parent directory to sys.path to allow importing auth
sys.path.insert(0, str(Path(__file__).parent))
from auth import OneNoteAuth

# ========== FIXTURE: Consistent MS_CLIENT_ID ==========
@pytest.fixture
def mock_env():
    """Fixture to set MS_CLIENT_ID environment variable."""
    with patch.dict(os.environ, {'MS_CLIENT_ID': 'test-client-id'}):
        yield

# ========== FIXED TESTS ==========

def test_init_resolves_token_path_home(mock_env):
    """Test that token path defaults to home directory when not in Docker."""
    # Mock Path.exists to simulate non-Docker environment
    with patch('pathlib.Path.exists', return_value=False):
        # Mock Path.home() to return a Path object, not a string
        mock_home_path = Path('/home/user')
        with patch('pathlib.Path.home', return_value=mock_home_path):
            auth = OneNoteAuth()
            expected = Path('/home/user/.onenote_rag/refresh_token')
            assert auth.token_path == expected


def test_init_resolves_token_path_docker(mock_env):
    """Test that token path uses /run/secrets when in Docker environment."""
    with patch('pathlib.Path.exists', return_value=True):
        auth = OneNoteAuth()
        assert str(auth.token_path) == '/run/secrets/ms_refresh_token'


def test_load_refresh_token_success(mock_env):
    """Test successfully loading a token from a file."""
    fake_token = "fake-refresh-token-123"
    # Mock both exists and read_text on the SAME Path instance
    mock_path = MagicMock(spec=Path)
    mock_path.exists.return_value = True
    mock_path.read_text.return_value = fake_token
    
    with patch('auth.Path', return_value=mock_path):
        auth = OneNoteAuth(token_path="/dummy/path")
        # The load happens in __init__, so check the instance variable
        assert auth.refresh_token == fake_token
        mock_path.read_text.assert_called_once()


def test_load_refresh_token_missing_file(mock_env):
    """Test handling a missing token file gracefully."""
    with patch('pathlib.Path.exists', return_value=False):
        auth = OneNoteAuth()
        assert auth.refresh_token is None


def test_save_refresh_token(mock_env):
    """Test that saving a token creates dirs and writes file securely."""
    # Create a mock Path object that tracks method calls
    mock_path = MagicMock(spec=Path)
    mock_parent = MagicMock()
    mock_path.parent = mock_parent
    # CRITICAL: Make exists() return False to trigger mkdir()
    mock_parent.exists.return_value = False

    with patch('auth.Path', return_value=mock_path):
        auth = OneNoteAuth(token_path="/dummy/path")
        test_token = "new-fake-token"

        auth._save_refresh_token(test_token)

        # First, verify exists() was checked
        mock_parent.exists.assert_called_once()
        # Now verify mkdir was called
        mock_parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        # Verify the file was written
        mock_path.write_text.assert_called_once_with(test_token)
        # Verify permissions were set (on non-Windows)
        if os.name != 'nt':
            mock_path.chmod.assert_called_once_with(0o600)


def test_token_saved_with_correct_permissions():
    """Integration test: does the token file get saved with 600 permissions?"""
    if os.name == 'nt':
        pytest.skip("Permissions test not relevant on Windows")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a custom token path in a temp dir
        test_token_path = Path(tmpdir) / "test_token"
        # Need to set MS_CLIENT_ID for this test
        with patch.dict(os.environ, {'MS_CLIENT_ID': 'test-client'}):
            auth = OneNoteAuth(token_path=str(test_token_path))
        
        # Simulate saving a new token
        test_token = "dummy_token_content"
        auth._save_refresh_token(test_token)
        
        # Verify the file was created and has correct permissions
        assert test_token_path.exists()
        # Check that file is readable/writable only by owner
        assert oct(test_token_path.stat().st_mode)[-3:] == '600'


def test_missing_client_id_raises_error():
    """Test that the class raises a clear error if MS_CLIENT_ID is missing."""
    with patch.object(OneNoteAuth, '_get_client_id', side_effect=ValueError("MS_CLIENT_ID must be set")):
        with pytest.raises(ValueError, match="MS_CLIENT_ID must be set"):
            OneNoteAuth()


@patch('auth.msal.PublicClientApplication')  # Patch the ACTUAL import source
def test_silent_token_refresh_success(mock_app_class, mock_env):
    """Test the happy path: silent refresh succeeds with a cached token."""
    # Setup the mock MSAL app and its successful response
    mock_app_instance = Mock()
    mock_app_class.return_value = mock_app_instance
    mock_app_instance.acquire_token_by_refresh_token.return_value = {
        'access_token': 'new-access-token-xyz',
        'refresh_token': 'new-refresh-token-abc'
    }
    
    # Create auth instance with a pre-existing "cached" refresh token
    with patch.object(OneNoteAuth, '_load_refresh_token', return_value='old-cached-token'):
        auth = OneNoteAuth()
        # Mock the _save_refresh_token method to track if it's called
        with patch.object(auth, '_save_refresh_token') as mock_save:
            token = auth.get_access_token()
    
    assert token == 'new-access-token-xyz'
    mock_save.assert_called_once_with('new-refresh-token-abc')


@patch('auth.msal.PublicClientApplication')  # Patch the ACTUAL import source
def test_silent_refresh_falls_back_to_device_flow(mock_app_class, mock_env):
    """Test that failed silent refresh triggers device flow."""
    mock_app_instance = Mock()
    mock_app_class.return_value = mock_app_instance
    
    # 1. First, silent refresh fails
    mock_app_instance.acquire_token_by_refresh_token.return_value = {
        'error': 'invalid_grant'
    }
    # 2. Then, device flow is initiated successfully
    mock_app_instance.initiate_device_flow.return_value = {
        'user_code': 'ABCD-EFGH',
        'verification_uri': 'https://microsoft.com/devicelogin'
    }
    mock_app_instance.acquire_token_by_device_flow.return_value = {
        'access_token': 'device-flow-access-token',
        'refresh_token': 'device-flow-refresh-token'
    }
    
    with patch.object(OneNoteAuth, '_load_refresh_token', return_value='expired-token'):
        auth = OneNoteAuth()
        with patch.object(auth, '_save_refresh_token'):
            token = auth.get_access_token()
    
    assert token == 'device-flow-access-token'
    # Verify both authentication methods were attempted
    mock_app_instance.acquire_token_by_refresh_token.assert_called_once()
    mock_app_instance.initiate_device_flow.assert_called_once()

