// Base API client
// For now, this is a mock implementation.
// When connecting to a real backend, replace this with axios or fetch.

const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

export const apiClient = {
  async get(endpoint) {
    await delay(600); // Simulate network latency
    console.log(`[API Mock] GET ${endpoint}`);
    // Real implementation would be:
    // const res = await fetch(`${import.meta.env.VITE_API_URL}${endpoint}`);
    // return res.json();
  },
  async post(endpoint, data) {
    await delay(800);
    console.log(`[API Mock] POST ${endpoint}`, data);
  }
};
