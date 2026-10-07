import { apiClient } from './api';

const ACTIVITY_FEED = [
  { id: 1, agent: 'hiring', task: 'Screening 12 engineering resumes', status: 'processing', time: 'Just now' },
  { id: 2, agent: 'knowledge', task: 'Updated employee handbook index', status: 'completed', time: '2m ago' },
  { id: 3, agent: 'research', task: 'Synthesized "Attention is All You Need"', status: 'completed', time: '15m ago' },
  { id: 4, agent: 'communication', task: 'Scheduled Q3 planning sync', status: 'completed', time: '1h ago' },
];

const COMM_SCHEDULE = [
  {
    id: 1,
    time: '09:00',
    title: 'Team Standup',
    duration: '30 min',
    participants: ['Marcus W.', 'Sarah C.', 'Jordan P.', '+4 more'],
    type: 'recurring',
    status: 'completed',
  },
  {
    id: 2,
    time: '11:30',
    title: 'HR Review',
    duration: '60 min',
    participants: ['Sarah C.', 'Marcus W.'],
    type: 'review',
    status: 'completed',
  },
  {
    id: 3,
    time: '16:00',
    title: 'Project Meeting',
    duration: '45 min',
    participants: ['Marcus W.', 'Jordan P.', 'Alex J.', 'Priya M.'],
    type: 'project',
    status: 'upcoming',
    hasAutomation: true,
  },
];

export const activityService = {
  /**
   * Fetch recent activity records.
   *
   * Reads the unified backend history covering Knowledge, Automation, and
   * Performance. Records are lightweight metadata only, so nothing here has
   * to render agent output. An empty history is a valid result, not an error,
   * so the empty list is returned rather than a fabricated fallback feed.
   *
   * @param {number} limit Maximum number of records to return.
   * @returns {Promise<Array<object>>} Records newest first.
   */
  async getActivityHistory(limit = 100) {
    const res = await apiClient.get(`/activity-history?limit=${limit}`);
    return res?.data || [];
  },

  async getRecentActivity() {
    const res = await apiClient.get('/activity/recent');
    return res?.data || ACTIVITY_FEED;
  },

  async getCommunicationSchedule() {
    try {
      const res = await apiClient.get('/communication/schedule');
      return res?.data || COMM_SCHEDULE;
    } catch {
      return COMM_SCHEDULE;
    }
  }
};
