import axios from 'axios';

export async function fetchModels() {
  const response = await axios.get('/api/models');
  return response.data;
}

export async function refreshModels() {
  const response = await axios.post('/api/models/refresh');
  return response.data;
}
