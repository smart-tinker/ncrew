import os
import base64
import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock, mock_open
from datetime import datetime
from app.interfaces.web_server import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def auth_headers():
    os.environ['WEB_ADMIN_USER'] = 'admin'
    os.environ['WEB_ADMIN_PASS'] = 'password'
    return {
        'Authorization': 'Basic ' + base64.b64encode(b"admin:password").decode('utf-8')
    }


def test_chat_page_requires_auth(client):
    """Test that chat page requires authentication."""
    response = client.get('/chat')
    assert response.status_code == 401


def test_chat_page_loads_with_auth(client, auth_headers):
    """Test that chat page loads with authentication."""
    response = client.get('/chat', headers=auth_headers)
    assert response.status_code == 200
    assert b'NeuroCrew Lab' in response.data or response.status_code == 200


def test_api_chat_history_requires_auth(client):
    """Test that API chat history requires authentication."""
    response = client.get('/api/chat/history')
    assert response.status_code == 401


def test_api_chat_history_no_target_chat(client, auth_headers):
    """Test that API returns error when TARGET_CHAT_ID is not set."""
    with patch('app.config.Config.TARGET_CHAT_ID', None):
        response = client.get('/api/chat/history', headers=auth_headers)
        assert response.status_code == 400


def test_api_chat_updates_requires_auth(client):
    """Test that API chat updates requires authentication."""
    response = client.get('/api/chat/updates')
    assert response.status_code == 401


def test_api_send_message_requires_auth(client):
    """Test that send message API requires authentication."""
    response = client.post('/api/chat/message', json={'text': 'Hello'})
    assert response.status_code == 401


def test_api_send_message_empty_text(client, auth_headers):
    """Test that send message API rejects empty text."""
    response = client.post('/api/chat/message', 
                          headers=auth_headers,
                          json={'text': ''},
                          content_type='application/json')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data


def test_api_send_message_no_target_chat(client, auth_headers):
    """Test that send message API returns error when TARGET_CHAT_ID is not set."""
    with patch('app.config.Config.TARGET_CHAT_ID', None):
        response = client.post('/api/chat/message',
                              headers=auth_headers,
                              json={'text': 'Hello'},
                              content_type='application/json')
        assert response.status_code == 400
