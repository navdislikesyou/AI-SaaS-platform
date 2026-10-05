import { apiClient } from './api';

const AGENTS = [
  {
    id: 'hiring',
    num: '01',
    name: 'Hiring AI',
    short: 'HIRING',
    path: '/agents/hiring',
    color: '#FF5A00',
    description: 'Recruit & analyze candidates',
  },
  {
    id: 'research',
    num: '02',
    name: 'Research AI',
    short: 'RESEARCH',
    path: '/agents/research',
    color: '#f5f4f0',
    description: 'Analyze papers & synthesize',
  },
  {
    id: 'knowledge',
    num: '03',
    name: 'Knowledge AI',
    short: 'KNOWLEDGE',
    path: '/agents/knowledge',
    color: '#E8FF72',
    description: 'Query organizational knowledge',
  },
  {
    id: 'communication',
    num: '04',
    name: 'Communication AI',
    short: 'COMM',
    path: '/agents/communication',
    color: '#17384D',
    colorLight: '#4a9dc4',
    description: 'Automate meeting & scheduling',
  },
  {
    id: 'insights',
    num: '05',
    name: 'Insights AI',
    short: 'INSIGHTS',
    path: '/agents/insights',
    color: '#FFFBE8',
    colorDark: '#c8c4b4',
    description: 'Analytics & org intelligence',
  },
];

export const agentService = {
  async getAgents() {
    await apiClient.get('/agents');
    return AGENTS;
  }
};
