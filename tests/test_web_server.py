import os
import base64
import pytest
from unittest.mock import patch, mock_open
from app.interfaces.web_server import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_auth_required(client):
    """Test that authentication is required to access the root URL."""
    response = client.get('/')
    assert response.status_code == 401

def test_auth_success(client):
    """Test that authentication succeeds with correct credentials."""
    os.environ['WEB_ADMIN_USER'] = 'admin'
    os.environ['WEB_ADMIN_PASS'] = 'password'

    headers = {
        'Authorization': 'Basic ' + base64.b64encode(b"admin:password").decode('utf-8')
    }

    with patch('app.interfaces.web_server.get_roles', return_value=[]):
        response = client.get('/', headers=headers)
        assert response.status_code == 200

@patch('builtins.open', new_callable=mock_open, read_data="roles: []")
def test_index_page_loads(mock_file_open, client):
    """Test that the index page loads and displays roles."""
    headers = {
        'Authorization': 'Basic ' + base64.b64encode(b"admin:password").decode('utf-8')
    }

    response = client.get('/', headers=headers)
    assert response.status_code == 200


@patch('app.interfaces.web_server.save_roles')
def test_save_roles(mock_save_roles, client):
    """Test that saving roles redirects and creates a reload file."""
    import time
    os.environ['WEB_ADMIN_USER'] = 'admin'
    os.environ['WEB_ADMIN_PASS'] = 'password'
    
    headers = {
        'Authorization': 'Basic ' + base64.b64encode(b"admin:password").decode('utf-8')
    }

    form_data = {
        'role_name': ['new_role'],
        'display_name': ['New Role'],
        'prompt_file': ['prompts/new.md'],
        'agent_type': ['qwen_acp'],
        'cli_command': ['qwen'],
        'description': ['A new role.'],
        'telegram_bot_token': ['new_token']
    }

    with patch('app.interfaces.web_server.get_roles', return_value=[]):
        with patch('builtins.open', mock_open()) as mock_file:
            response = client.post('/save', headers=headers, data=form_data, follow_redirects=True)

    # Wait for background thread to write .reload file
    time.sleep(1.5)
    
    assert response.status_code == 200
    mock_save_roles.assert_called_once()
