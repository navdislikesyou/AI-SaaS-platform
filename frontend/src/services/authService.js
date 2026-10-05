import { apiClient } from './api';

const DEMO_USERS = {
  owner: {
    id: 'usr_001',
    name: 'Marcus Webb',
    email: 'marcus@axiom-corp.com',
    role: 'Organization Owner',
    accessLevel: 'Global',
    organization: 'Axiom Corp',
    avatar: 'MW',
    permissions: {
      hiring: 'full',
      research: 'full',
      knowledge: 'full',
      communication: 'full',
      insights: 'full',
    },
  },
  hr_admin: {
    id: 'usr_002',
    name: 'Sarah Chen',
    email: 'sarah@axiom-corp.com',
    role: 'HR Super Admin',
    accessLevel: 'Department',
    organization: 'Axiom Corp',
    avatar: 'SC',
    permissions: {
      hiring: 'full',
      research: 'none',
      knowledge: 'limited',
      communication: 'full',
      insights: 'limited',
    },
  },
  employee: {
    id: 'usr_003',
    name: 'Jordan Park',
    email: 'jordan@axiom-corp.com',
    role: 'Employee',
    accessLevel: 'Personal',
    organization: 'Axiom Corp',
    avatar: 'JP',
    permissions: {
      hiring: 'none',
      research: 'none',
      knowledge: 'limited',
      communication: 'full',
      insights: 'none',
    },
  },
};

export const authService = {
  async login(email, password) {
    await apiClient.post('/auth/login', { email });
    
    // Mock logic
    let selectedUser = DEMO_USERS.owner;
    if (email.toLowerCase().includes('sarah') || email.toLowerCase().includes('hr')) {
      selectedUser = DEMO_USERS.hr_admin;
    } else if (email.toLowerCase().includes('jordan') || email.toLowerCase().includes('employee')) {
      selectedUser = DEMO_USERS.employee;
    }
    return selectedUser;
  },
  
  async logout() {
    await apiClient.post('/auth/logout');
    return true;
  }
};
