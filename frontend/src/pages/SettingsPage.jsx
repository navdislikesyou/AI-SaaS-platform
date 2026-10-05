import React, { useState } from 'react';
import Navigation from '../components/Navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../context/AuthContext';

const BASE_TABS = [
  { id: 'profile', label: 'Account Profile' },
  { id: 'ai', label: 'AI Preferences' },
  { id: 'api', label: 'API Keys' },
  { id: 'notifications', label: 'Notifications' },
];

const ADMIN_TABS = [
  { id: 'users', label: 'User Directory' },
  { id: 'access', label: 'Access Control' },
];

export default function SettingsPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('profile');
  
  // Modal states
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [isAccessModalOpen, setIsAccessModalOpen] = useState(false);
  const [selectedAgentForAccess, setSelectedAgentForAccess] = useState(null);
  
  // Custom dropdown states
  const [roleDropdownOpen, setRoleDropdownOpen] = useState(false);
  const [selectedRole, setSelectedRole] = useState('Employee');

  const TABS = user?.accessLevel === 'Global' ? [...BASE_TABS, ...ADMIN_TABS] : BASE_TABS;

  return (
    <div className="agent-page">
      <Navigation />
      <main className="agent-main" style={{ overflowY: 'auto', padding: '40px 64px' }}>
        <motion.div
          className="settings-content"
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          style={{ maxWidth: '1200px', margin: '0 auto', width: '100%', paddingTop: '24px' }}
        >
          <div className="placeholder-label" style={{ color: 'var(--soft-lime)' }}>Settings</div>
          <h1 className="placeholder-heading" style={{ fontSize: '3.5rem', marginBottom: '40px', color: '#f5f4f0', fontWeight: '800', letterSpacing: '-0.02em' }}>
            WORKSPACE SETTINGS
          </h1>
          
          <div style={{ display: 'flex', gap: '64px', alignItems: 'flex-start' }}>
            {/* Sidebar */}
            <div style={{ width: '240px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {TABS.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  style={{
                    background: activeTab === tab.id ? 'rgba(255,255,255,0.05)' : 'transparent',
                    border: '1px solid',
                    borderColor: activeTab === tab.id ? 'rgba(255,255,255,0.1)' : 'transparent',
                    color: activeTab === tab.id ? '#f5f4f0' : 'rgba(255,255,255,0.5)',
                    padding: '12px 16px',
                    borderRadius: '6px',
                    textAlign: 'left',
                    fontSize: '0.875rem',
                    fontWeight: 500,
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Content Area */}
            <div style={{ flex: 1 }}>
              <AnimatePresence mode="wait">
                {activeTab === 'profile' && (
                  <motion.div key="profile" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                    <div className="settings-section">
                      <h2 className="heading-medium" style={{ fontSize: '1.25rem', marginBottom: '24px' }}>Account Profile</h2>
                      <div className="settings-card" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '32px' }}>
                        
                        <div style={{ display: 'flex', alignItems: 'center', gap: '24px', marginBottom: '32px' }}>
                          <div style={{ position: 'relative' }}>
                            <div style={{ width: '80px', height: '80px', borderRadius: '50%', background: 'var(--soft-lime)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#060605', fontSize: '1.5rem', fontWeight: 'bold' }}>
                              {user?.avatar || 'US'}
                            </div>
                            <button style={{ position: 'absolute', bottom: -4, right: -4, background: '#1c1c1c', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '50%', width: '28px', height: '28px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#f5f4f0' }}>
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" />
                              </svg>
                            </button>
                          </div>
                          <div>
                            <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#f5f4f0' }}>{user?.name || 'Not logged in'}</h3>
                            <p style={{ color: 'var(--soft-lime)', fontSize: '0.875rem', marginTop: '4px', fontWeight: 500 }}>{user?.role || 'Guest'}</p>
                          </div>
                        </div>

                        <div className="divider" style={{ height: '1px', background: 'rgba(255,255,255,0.05)', margin: '24px 0' }} />

                        <div className="settings-row" style={{ display: 'flex', gap: '40px' }}>
                          <div style={{ flex: 1 }}>
                            <h3 style={{ fontSize: '1rem', fontWeight: 500, color: '#f5f4f0' }}>Email Address</h3>
                            <p className="body-text" style={{ fontSize: '0.875rem', marginTop: '4px', opacity: 0.8 }}>{user?.email || '—'}</p>
                          </div>
                          <div style={{ flex: 1 }}>
                            <h3 style={{ fontSize: '1rem', fontWeight: 500, color: '#f5f4f0' }}>Organization</h3>
                            <p className="body-text" style={{ fontSize: '0.875rem', marginTop: '4px', opacity: 0.8 }}>{user?.organization || '—'}</p>
                          </div>
                        </div>
                        
                        <div className="divider" style={{ height: '1px', background: 'rgba(255,255,255,0.05)', margin: '24px 0' }} />
                        
                        <div className="settings-row" style={{ display: 'flex', gap: '40px' }}>
                          <div style={{ flex: 1 }}>
                            <h3 style={{ fontSize: '1rem', fontWeight: 500, color: '#f5f4f0' }}>Access Level</h3>
                            <p className="body-text" style={{ fontSize: '0.875rem', marginTop: '4px', opacity: 0.8 }}>{user?.accessLevel || '—'} Access</p>
                          </div>
                          <div style={{ flex: 1 }}>
                            <h3 style={{ fontSize: '1rem', fontWeight: 500, color: '#f5f4f0' }}>User ID</h3>
                            <p className="body-text" style={{ fontSize: '0.875rem', marginTop: '4px', opacity: 0.8, fontFamily: 'monospace' }}>{user?.id || '—'}</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </motion.div>
                )}

                {activeTab === 'ai' && (
                  <motion.div key="ai" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                    <div className="settings-section">
                      <h2 className="heading-medium" style={{ fontSize: '1.25rem', marginBottom: '24px' }}>AI Preferences</h2>
                      <div className="settings-card" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '32px' }}>
                        <div className="settings-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div>
                            <h3 style={{ fontSize: '1rem', fontWeight: 500, color: '#f5f4f0' }}>Strict Output Formatting</h3>
                            <p className="body-text" style={{ fontSize: '0.875rem', marginTop: '4px' }}>Force agents to strictly adhere to requested schemas.</p>
                          </div>
                          <div style={{ width: '44px', height: '24px', background: 'var(--soft-lime)', borderRadius: '12px', position: 'relative', cursor: 'pointer', flexShrink: 0 }}>
                            <div style={{ width: '20px', height: '20px', background: '#000', borderRadius: '50%', position: 'absolute', top: '2px', right: '2px' }} />
                          </div>
                        </div>
                        <div className="divider" style={{ margin: '24px 0', opacity: 0.5, borderTop: '1px solid rgba(255,255,255,0.05)' }} />
                        <div className="settings-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 0 }}>
                          <div>
                            <h3 style={{ fontSize: '1rem', fontWeight: 500, color: '#f5f4f0' }}>Verbose Logging</h3>
                            <p className="body-text" style={{ fontSize: '0.875rem', marginTop: '4px' }}>Enable detailed trace logs for agent reasoning.</p>
                          </div>
                          <div style={{ width: '44px', height: '24px', background: 'rgba(255,255,255,0.1)', borderRadius: '12px', position: 'relative', cursor: 'pointer', flexShrink: 0 }}>
                            <div style={{ width: '20px', height: '20px', background: '#888', borderRadius: '50%', position: 'absolute', top: '2px', left: '2px' }} />
                          </div>
                        </div>
                      </div>
                    </div>
                  </motion.div>
                )}

                {activeTab === 'api' && (
                  <motion.div key="api" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                    <div className="settings-section">
                      <h2 className="heading-medium" style={{ fontSize: '1.25rem', marginBottom: '24px' }}>API Keys</h2>
                      <div className="settings-card" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '32px' }}>
                        <p className="body-text" style={{ marginBottom: '24px', opacity: 0.8 }}>Manage your secret keys for external integrations. Treat these like passwords.</p>
                        <div style={{ background: 'rgba(0,0,0,0.2)', padding: '16px', borderRadius: '6px', fontFamily: 'JetBrains Mono', fontSize: '0.875rem', color: 'rgba(255,255,255,0.6)', marginBottom: '24px' }}>
                          sk_test_••••••••••••••••••••
                        </div>
                        <button style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.2)', color: '#f5f4f0', padding: '10px 20px', borderRadius: '6px', fontSize: '0.875rem', cursor: 'pointer' }}>+ Generate New Key</button>
                      </div>
                    </div>
                  </motion.div>
                )}
                
                {activeTab === 'notifications' && (
                  <motion.div key="notifications" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                    <div className="settings-section">
                      <h2 className="heading-medium" style={{ fontSize: '1.25rem', marginBottom: '24px' }}>Notifications</h2>
                      <div className="settings-card" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '32px' }}>
                        
                        <div className="settings-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div>
                            <h3 style={{ fontSize: '1rem', fontWeight: 500, color: '#f5f4f0' }}>Agent Task Completions</h3>
                            <p className="body-text" style={{ fontSize: '0.875rem', marginTop: '4px' }}>Get notified when an AI agent finishes a background task.</p>
                          </div>
                          <div style={{ width: '44px', height: '24px', background: 'var(--soft-lime)', borderRadius: '12px', position: 'relative', cursor: 'pointer', flexShrink: 0 }}>
                            <div style={{ width: '20px', height: '20px', background: '#000', borderRadius: '50%', position: 'absolute', top: '2px', right: '2px' }} />
                          </div>
                        </div>

                        <div className="divider" style={{ margin: '24px 0', opacity: 0.5, borderTop: '1px solid rgba(255,255,255,0.05)' }} />

                        <div className="settings-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div>
                            <h3 style={{ fontSize: '1rem', fontWeight: 500, color: '#f5f4f0' }}>System Errors & Warnings</h3>
                            <p className="body-text" style={{ fontSize: '0.875rem', marginTop: '4px' }}>Critical alerts if an integration or API fails.</p>
                          </div>
                          <div style={{ width: '44px', height: '24px', background: 'var(--soft-lime)', borderRadius: '12px', position: 'relative', cursor: 'pointer', flexShrink: 0 }}>
                            <div style={{ width: '20px', height: '20px', background: '#000', borderRadius: '50%', position: 'absolute', top: '2px', right: '2px' }} />
                          </div>
                        </div>

                        <div className="divider" style={{ margin: '24px 0', opacity: 0.5, borderTop: '1px solid rgba(255,255,255,0.05)' }} />

                        <div className="settings-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div>
                            <h3 style={{ fontSize: '1rem', fontWeight: 500, color: '#f5f4f0' }}>Daily Workspace Digest</h3>
                            <p className="body-text" style={{ fontSize: '0.875rem', marginTop: '4px' }}>Receive a daily email summarizing all AI activity.</p>
                          </div>
                          <div style={{ width: '44px', height: '24px', background: 'rgba(255,255,255,0.1)', borderRadius: '12px', position: 'relative', cursor: 'pointer', flexShrink: 0 }}>
                            <div style={{ width: '20px', height: '20px', background: '#888', borderRadius: '50%', position: 'absolute', top: '2px', left: '2px' }} />
                          </div>
                        </div>

                      </div>
                    </div>
                  </motion.div>
                )}

                {activeTab === 'users' && (
                  <motion.div key="users" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                    <div className="settings-section">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                        <h2 className="heading-medium" style={{ fontSize: '1.25rem' }}>User Directory</h2>
                        <button onClick={() => setIsInviteModalOpen(true)} style={{ background: 'var(--soft-lime)', color: '#000', border: 'none', padding: '8px 16px', borderRadius: '4px', fontWeight: 600, fontSize: '0.875rem', cursor: 'pointer' }}>+ Invite User</button>
                      </div>
                      <div className="settings-card" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', overflow: 'hidden' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                          <thead>
                            <tr style={{ background: 'rgba(255,255,255,0.05)', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                              <th style={{ padding: '16px', fontSize: '0.875rem', fontWeight: 500, color: 'rgba(255,255,255,0.5)' }}>Name & Email</th>
                              <th style={{ padding: '16px', fontSize: '0.875rem', fontWeight: 500, color: 'rgba(255,255,255,0.5)' }}>Role</th>
                              <th style={{ padding: '16px', fontSize: '0.875rem', fontWeight: 500, color: 'rgba(255,255,255,0.5)' }}>Organization</th>
                              <th style={{ padding: '16px', fontSize: '0.875rem', fontWeight: 500, color: 'rgba(255,255,255,0.5)' }}>Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                              <td style={{ padding: '16px' }}>
                                <div style={{ fontSize: '0.875rem', color: '#f5f4f0', fontWeight: 500 }}>Marcus Webb</div>
                                <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)', marginTop: '4px' }}>marcus@axiom-corp.com</div>
                              </td>
                              <td style={{ padding: '16px', fontSize: '0.875rem', color: 'var(--soft-lime)' }}>Org Owner</td>
                              <td style={{ padding: '16px', fontSize: '0.875rem', color: '#f5f4f0' }}>Axiom Corp</td>
                              <td style={{ padding: '16px' }}><span style={{ padding: '4px 8px', background: 'rgba(0,255,0,0.1)', color: '#4ade80', borderRadius: '12px', fontSize: '0.75rem' }}>Active</span></td>
                            </tr>
                            <tr>
                              <td style={{ padding: '16px' }}>
                                <div style={{ fontSize: '0.875rem', color: '#f5f4f0', fontWeight: 500 }}>Sarah Chen</div>
                                <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)', marginTop: '4px' }}>sarah@axiom-corp.com</div>
                              </td>
                              <td style={{ padding: '16px', fontSize: '0.875rem', color: '#f5f4f0' }}>Employee</td>
                              <td style={{ padding: '16px', fontSize: '0.875rem', color: '#f5f4f0' }}>Axiom Corp</td>
                              <td style={{ padding: '16px' }}><span style={{ padding: '4px 8px', background: 'rgba(0,255,0,0.1)', color: '#4ade80', borderRadius: '12px', fontSize: '0.75rem' }}>Active</span></td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </motion.div>
                )}

                {activeTab === 'access' && (
                  <motion.div key="access" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                    <div className="settings-section">
                      <h2 className="heading-medium" style={{ fontSize: '1.25rem', marginBottom: '24px' }}>Access Control</h2>
                      <div className="settings-card" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '32px' }}>
                        <p className="body-text" style={{ marginBottom: '24px', opacity: 0.8 }}>Manage which roles have access to specific AI agents and workflows.</p>
                        
                        <div className="settings-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div>
                            <h3 style={{ fontSize: '1rem', fontWeight: 500, color: '#f5f4f0' }}>Hiring AI Access</h3>
                            <p className="body-text" style={{ fontSize: '0.875rem', marginTop: '4px' }}>Only Org Owners and HR roles.</p>
                          </div>
                          <button onClick={() => { setSelectedAgentForAccess('Hiring AI'); setIsAccessModalOpen(true); }} style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.2)', color: '#f5f4f0', padding: '8px 16px', borderRadius: '4px', fontSize: '0.75rem', cursor: 'pointer' }}>Edit Access</button>
                        </div>
                        <div className="divider" style={{ margin: '24px 0', opacity: 0.5, borderTop: '1px solid rgba(255,255,255,0.05)' }} />
                        <div className="settings-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div>
                            <h3 style={{ fontSize: '1rem', fontWeight: 500, color: '#f5f4f0' }}>Knowledge Base AI Access</h3>
                            <p className="body-text" style={{ fontSize: '0.875rem', marginTop: '4px' }}>Available to all Employees (Global).</p>
                          </div>
                          <button onClick={() => { setSelectedAgentForAccess('Knowledge Base AI'); setIsAccessModalOpen(true); }} style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.2)', color: '#f5f4f0', padding: '8px 16px', borderRadius: '4px', fontSize: '0.75rem', cursor: 'pointer' }}>Edit Access</button>
                        </div>

                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </motion.div>
      </main>

      {/* Invite User Modal */}
      <AnimatePresence>
        {isInviteModalOpen && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.8)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 20, opacity: 0 }} style={{ background: '#1c1c1c', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', padding: '32px', width: '100%', maxWidth: '400px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#f5f4f0' }}>Invite New User</h3>
                <button onClick={() => setIsInviteModalOpen(false)} style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer', fontSize: '1.25rem' }}>×</button>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.875rem', color: 'rgba(255,255,255,0.7)', marginBottom: '8px' }}>Email Address</label>
                  <input type="email" placeholder="name@company.com" style={{ width: '100%', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', padding: '12px', borderRadius: '6px', color: '#f5f4f0', outline: 'none' }} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.875rem', color: 'rgba(255,255,255,0.7)', marginBottom: '8px' }}>Role</label>
                  <div style={{ position: 'relative' }}>
                    <div 
                      onClick={() => setRoleDropdownOpen(!roleDropdownOpen)}
                      style={{ width: '100%', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', padding: '12px', borderRadius: '6px', color: '#f5f4f0', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                    >
                      <span>{selectedRole}</span>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.5, transform: roleDropdownOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
                        <polyline points="6 9 12 15 18 9"></polyline>
                      </svg>
                    </div>
                    <AnimatePresence>
                      {roleDropdownOpen && (
                        <motion.div 
                          initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }} transition={{ duration: 0.15 }}
                          style={{ position: 'absolute', top: '100%', left: 0, right: 0, marginTop: '4px', background: '#1c1c1c', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', overflow: 'hidden', zIndex: 10, boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}
                        >
                          {['Employee', 'HR Manager', 'Organization Owner'].map(r => (
                            <div 
                              key={r} 
                              onClick={() => { setSelectedRole(r); setRoleDropdownOpen(false); }}
                              style={{ padding: '12px 16px', cursor: 'pointer', background: selectedRole === r ? 'rgba(255,255,255,0.05)' : 'transparent', color: selectedRole === r ? 'var(--soft-lime)' : '#f5f4f0', fontSize: '0.875rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
                            >
                              {r}
                              {selectedRole === r && <span style={{ color: 'var(--soft-lime)' }}>✓</span>}
                            </div>
                          ))}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </div>
              </div>
              <div style={{ marginTop: '32px', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                <button onClick={() => setIsInviteModalOpen(false)} style={{ background: 'transparent', color: '#f5f4f0', border: '1px solid rgba(255,255,255,0.2)', padding: '10px 20px', borderRadius: '6px', cursor: 'pointer' }}>Cancel</button>
                <button onClick={() => setIsInviteModalOpen(false)} style={{ background: 'var(--soft-lime)', color: '#000', border: 'none', padding: '10px 20px', borderRadius: '6px', fontWeight: 600, cursor: 'pointer' }}>Send Invite</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Edit Access Modal */}
      <AnimatePresence>
        {isAccessModalOpen && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.8)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 20, opacity: 0 }} style={{ background: '#1c1c1c', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', padding: '32px', width: '100%', maxWidth: '400px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#f5f4f0' }}>Edit Access: {selectedAgentForAccess}</h3>
                <button onClick={() => setIsAccessModalOpen(false)} style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer', fontSize: '1.25rem' }}>×</button>
              </div>
              <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.875rem', marginBottom: '24px' }}>Select which roles can interact with this AI Agent.</p>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {['Organization Owner', 'HR Manager', 'Employee', 'Guest'].map((role) => (
                  <label key={role} style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px', background: 'rgba(255,255,255,0.02)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.05)', cursor: 'pointer' }}>
                    <input type="checkbox" defaultChecked={role === 'Organization Owner' || role === 'HR Manager'} style={{ width: '18px', height: '18px', accentColor: 'var(--soft-lime)' }} />
                    <span style={{ color: '#f5f4f0', fontSize: '0.875rem' }}>{role}</span>
                  </label>
                ))}
              </div>

              <div style={{ marginTop: '32px', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                <button onClick={() => setIsAccessModalOpen(false)} style={{ background: 'transparent', color: '#f5f4f0', border: '1px solid rgba(255,255,255,0.2)', padding: '10px 20px', borderRadius: '6px', cursor: 'pointer' }}>Cancel</button>
                <button onClick={() => setIsAccessModalOpen(false)} style={{ background: 'var(--soft-lime)', color: '#000', border: 'none', padding: '10px 20px', borderRadius: '6px', fontWeight: 600, cursor: 'pointer' }}>Save Changes</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

    </div>
  );
}
