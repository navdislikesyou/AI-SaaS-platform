import { apiClient } from './api';

// UI Presentation metadata paired with backend agent keys
const AGENT_METADATA = {
  knowledge: {
    num: '01',
    name: 'Knowledge AI',
    displayName: 'Knowledge',
    short: 'KNOWLEDGE',
    path: '/agents/knowledge',
    color: '#E8FF72',
    colorLight: '#E8FF72',
    bg: '#090a00',
    tagline: 'Ask your organization anything.',
    category: 'RAG & Document Intelligence',
    defaultOperation: 'query',
    samplePayload: { question: 'What is our employee leave policy?' },
    executionPath: 'execute',
  },
  automation: {
    num: '02',
    name: 'Automation AI',
    displayName: 'Automation',
    short: 'AUTOMATION',
    path: '/agents/automation',
    color: '#4A9DC4',
    colorLight: '#7ad0fa',
    bg: '#000a0d',
    tagline: 'Turn productivity requests into draft actions.',
    category: 'Workflow & Task Automation',
    defaultOperation: 'draft_action',
    // The adapter requires `instruction`, not `prompt`.
    samplePayload: { instruction: 'Schedule a quarterly sync with leadership' },
    executionPath: 'execute',
  },
  performance: {
    num: '03',
    name: 'Performance AI',
    displayName: 'Performance Analyzer',
    short: 'PERFORMANCE',
    path: '/agents/performance',
    color: '#FF5A00',
    colorLight: '#ff8533',
    bg: '#0d0400',
    tagline: 'Data analytics, KPIs, trends, and operational insights.',
    category: 'Analytics & Insights Engine',
    // Performance is NOT executable through /agents/execute. Its operations run
    // as background jobs, so it advertises no capabilities in the catalog and
    // carries no defaultOperation or samplePayload.
    executionPath: 'jobs',
  },
};

// Planned agents for roadmap
const ROADMAP_AGENTS = [
  {
    id: 'hiring',
    name: 'Hiring AI',
    displayName: 'Hiring',
    num: '04',
    short: 'HIRING',
    path: '/agents/hiring',
    color: '#FF9500',
    colorLight: '#ffaa33',
    bg: '#140800',
    tagline: 'Automate candidate screening and recruitment.',
    description: 'AI-assisted resume screening, candidate matching, and interview evaluation workflows.',
    capabilities: ['resume_screening', 'candidate_matching', 'interview_scheduling'],
    status: 'roadmap',
    available: false,
    isRoadmap: true,
  },
  {
    id: 'research',
    name: 'Research AI',
    displayName: 'Research',
    num: '05',
    short: 'RESEARCH',
    path: '/agents/research',
    color: '#D4B8FF',
    colorLight: '#e4d4ff',
    bg: '#0a0014',
    tagline: 'Synthesize research papers and market intelligence.',
    description: 'Literature analysis, academic paper synthesis, topic relevance scoring, and method extraction.',
    capabilities: ['paper_synthesis', 'method_extraction', 'topic_scoring'],
    status: 'roadmap',
    available: false,
    isRoadmap: true,
  },
];

export const agentService = {
  /**
   * Fetch agents catalog from FastAPI backend and enrich with UI presentation config.
   */
  async getAgents() {
    try {
      const response = await apiClient.get('/agents');
      const backendAgents = response?.data?.agents || [];

      // Merge backend agents with presentation metadata
      const liveAgents = backendAgents.map((bAgent) => {
        const meta = AGENT_METADATA[bAgent.name] || {
          num: '00',
          name: bAgent.display_name,
          displayName: bAgent.display_name,
          short: bAgent.name.toUpperCase(),
          path: `/agents/${bAgent.name}`,
          color: '#ffffff',
          colorLight: '#ffffff',
          bg: '#111111',
          tagline: 'Enterprise autonomous agent.',
          category: 'AI Worker',
          defaultOperation: bAgent.capabilities?.[0] || 'execute',
          samplePayload: {},
          executionPath: 'execute',
        };

        // An agent advertising no capabilities is not broken: it is served by a
        // different endpoint. The backend reports `capabilities: []` for
        // Performance because its work runs as a background job. Normalize that
        // here so components read `executionPath` instead of branching on name.
        const capabilities = bAgent.capabilities || [];
        const executionPath =
          meta.executionPath || (capabilities.length === 0 ? 'jobs' : 'execute');

        return {
          id: bAgent.name,
          num: meta.num,
          name: meta.name,
          displayName: bAgent.display_name,
          short: meta.short,
          path: meta.path,
          color: meta.color,
          colorLight: meta.colorLight,
          bg: meta.bg,
          tagline: meta.tagline,
          description: bAgent.description,
          capabilities,
          status: bAgent.status, // 'ready' or 'not_connected'
          available: bAgent.available,
          isBackend: true,
          executionPath,
          defaultOperation: meta.defaultOperation,
          samplePayload: meta.samplePayload,
        };
      });

      return [...liveAgents, ...ROADMAP_AGENTS];
    } catch (error) {
      console.warn('[agentService] Failed to load backend agents, using cached registry', error?.message);
      // Fallback cache if backend is disconnected
      const fallbackLive = Object.entries(AGENT_METADATA).map(([key, meta]) => ({
        id: key,
        ...meta,
        description: 'Autonomous enterprise workforce agent.',
        capabilities: meta.executionPath === 'jobs' ? [] : ['query', 'execute'],
        status: 'not_connected',
        available: false,
        isBackend: true,
      }));
      return [...fallbackLive, ...ROADMAP_AGENTS];
    }
  },

  /**
   * Get metadata for a specific agent.
   */
  async getAgent(name) {
    const res = await apiClient.get(`/agents/${name}`);
    return res?.data;
  },

  /**
   * Execute an operation on an agent via POST /api/v1/agents/execute.
   */
  async executeAgent(agentName, operation, payload = {}) {
    return apiClient.post('/agents/execute', {
      agent: agentName,
      operation,
      payload,
    });
  },
};
