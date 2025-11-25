import os
import base64
import pytest
from unittest.mock import patch, MagicMock
from app.interfaces.web.server import app

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

@patch('app.interfaces.web.server.multi_project_manager')
def test_list_projects(mock_mpm, client, auth_headers):
    """Test listing projects."""
    mock_mpm.list_projects.return_value = ['default', 'project2']
    mock_mpm.get_current_project.return_value = 'default'
    
    response = client.get('/api/projects/list', headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data['projects'] == ['default', 'project2']
    assert data['current_project'] == 'default'

@patch('app.interfaces.web.server.multi_project_manager')
def test_create_project_success(mock_mpm, client, auth_headers):
    """Test creating a new project."""
    mock_mpm.project_exists.return_value = False
    
    response = client.post('/api/projects/create', headers=auth_headers, json={
        'project_name': 'new_project'
    })
    
    assert response.status_code == 200
    assert response.get_json()['success'] is True
    mock_mpm.create_project.assert_called_with('new_project')
    mock_mpm.load_project_config.assert_called_with('new_project')

@patch('app.interfaces.web.server.multi_project_manager')
def test_create_project_existing(mock_mpm, client, auth_headers):
    """Test creating an existing project fails."""
    mock_mpm.project_exists.return_value = True
    
    response = client.post('/api/projects/create', headers=auth_headers, json={
        'project_name': 'existing_project'
    })
    
    assert response.status_code == 400
    assert 'already exists' in response.get_json()['error']

@patch('app.interfaces.web.server.multi_project_manager')
def test_switch_project_success(mock_mpm, client, auth_headers):
    """Test switching project."""
    mock_mpm.project_exists.return_value = True
    
    response = client.post('/api/projects/switch', headers=auth_headers, json={
        'project_name': 'project2'
    })
    
    assert response.status_code == 200
    assert response.get_json()['success'] is True
    mock_mpm.load_project_config.assert_called_with('project2')

@patch('app.interfaces.web.server.multi_project_manager')
def test_switch_project_not_found(mock_mpm, client, auth_headers):
    """Test switching to non-existent project fails."""
    mock_mpm.project_exists.return_value = False
    
    response = client.post('/api/projects/switch', headers=auth_headers, json={
        'project_name': 'nonexistent'
    })
    
    assert response.status_code == 404
    assert 'not found' in response.get_json()['error']
