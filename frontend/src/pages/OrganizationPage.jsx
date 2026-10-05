import React, { useState } from 'react';
import Navigation from '../components/Navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';

const TABS = [
  { id: 'directory', label: 'Directory' },
  { id: 'add', label: 'Add Employee' },
  { id: 'teams', label: 'Teams' },
  { id: 'analytics', label: 'Analytics' }
];

const USERS = [
  { name: 'Marcus Webb', role: 'Org Owner', email: 'marcus@axiom-corp.com', time: 'Active Now', team: 'Management', status: 'Active' },
  { name: 'Sarah Chen', role: 'Employee', email: 'sarah@axiom-corp.com', time: '2h ago', team: 'Engineering', status: 'Active' },
  { name: 'Alex Rivera', role: 'Admin', email: 'alex@axiom-corp.com', time: 'Just now', team: 'IT', status: 'Active' },
  { name: 'Priya Patel', role: 'Manager', email: 'priya@axiom-corp.com', time: '1d ago', team: 'Marketing', status: 'Invited' },
];

const TEAMS = [
  { name: 'Engineering', employees: 12, agents: 4 },
  { name: 'Marketing', employees: 5, agents: 2 },
  { name: 'HR & Ops', employees: 3, agents: 1 },
  { name: 'Management', employees: 2, agents: 5 },
];

export default function OrganizationPage() {
  const [activeTab, setActiveTab] = useState('directory');

  // States for Employee Dropdowns
  const [roleDropdownOpen, setRoleDropdownOpen] = useState(false);
  const [selectedRole, setSelectedRole] = useState('Employee');
  
  const [teamDropdownOpen, setTeamDropdownOpen] = useState(false);
  const [selectedTeam, setSelectedTeam] = useState('Engineering');

  return (
    <div className="agent-page">
      <Navigation />
      <main className="agent-main" style={{ overflowY: 'auto', padding: '40px 64px' }}>
        <motion.div
          className="org-content"
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          style={{ maxWidth: '1200px', margin: '0 auto', width: '100%', paddingTop: '24px' }}
        >
          <div className="placeholder-label" style={{ color: 'var(--soft-lime)' }}>Organization</div>
          <h1 className="placeholder-heading" style={{ fontSize: '3.5rem', marginBottom: '40px', color: '#f5f4f0', fontWeight: '800', letterSpacing: '-0.02em', textTransform: 'uppercase' }}>
            Axiom Corp
          </h1>

          {/* Horizontal Tabs */}
          <div style={{ display: 'flex', gap: '8px', marginBottom: '40px', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '16px' }}>
            {TABS.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  background: activeTab === tab.id ? 'rgba(255,255,255,0.05)' : 'transparent',
                  border: '1px solid',
                  borderColor: activeTab === tab.id ? 'rgba(255,255,255,0.1)' : 'transparent',
                  color: activeTab === tab.id ? '#f5f4f0' : 'rgba(255,255,255,0.5)',
                  padding: '8px 24px',
                  borderRadius: '20px',
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

          <AnimatePresence mode="wait">
            {/* DIRECTORY TAB */}
            {activeTab === 'directory' && (
              <motion.div key="directory" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                  <h2 className="heading-medium" style={{ fontSize: '1.25rem' }}>Employees</h2>
                  <button onClick={() => setActiveTab('add')} style={{ background: 'var(--soft-lime)', color: '#000', border: 'none', padding: '8px 16px', borderRadius: '4px', fontWeight: 600, fontSize: '0.875rem', cursor: 'pointer' }}>+ Invite Employee</button>
                </div>
                <div className="settings-card" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', overflow: 'hidden' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                    <thead>
                      <tr style={{ background: 'rgba(255,255,255,0.05)', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                        <th style={{ padding: '16px', fontSize: '0.875rem', fontWeight: 500, color: 'rgba(255,255,255,0.5)' }}>Name & Email</th>
                        <th style={{ padding: '16px', fontSize: '0.875rem', fontWeight: 500, color: 'rgba(255,255,255,0.5)' }}>Role</th>
                        <th style={{ padding: '16px', fontSize: '0.875rem', fontWeight: 500, color: 'rgba(255,255,255,0.5)' }}>Team</th>
                        <th style={{ padding: '16px', fontSize: '0.875rem', fontWeight: 500, color: 'rgba(255,255,255,0.5)' }}>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {USERS.map((u, i) => (
                        <tr key={i} style={{ borderBottom: i === USERS.length - 1 ? 'none' : '1px solid rgba(255,255,255,0.05)' }}>
                          <td style={{ padding: '16px' }}>
                            <div style={{ fontSize: '0.875rem', color: '#f5f4f0', fontWeight: 500 }}>{u.name}</div>
                            <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)', marginTop: '4px' }}>{u.email}</div>
                          </td>
                          <td style={{ padding: '16px', fontSize: '0.875rem', color: u.role === 'Org Owner' ? 'var(--soft-lime)' : '#f5f4f0' }}>{u.role}</td>
                          <td style={{ padding: '16px', fontSize: '0.875rem', color: '#f5f4f0' }}>{u.team}</td>
                          <td style={{ padding: '16px' }}>
                            <span style={{ padding: '4px 8px', background: u.status === 'Active' ? 'rgba(0,255,0,0.1)' : 'rgba(255,165,0,0.1)', color: u.status === 'Active' ? '#4ade80' : '#ffa500', borderRadius: '12px', fontSize: '0.75rem' }}>
                              {u.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </motion.div>
            )}

            {/* ADD EMPLOYEE TAB */}
            {activeTab === 'add' && (
              <motion.div key="add" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                <div style={{ maxWidth: '600px', margin: '0 auto' }}>
                  <h2 className="heading-medium" style={{ fontSize: '1.5rem', marginBottom: '8px', textAlign: 'center' }}>Invite a New Employee</h2>
                  <p className="body-text" style={{ textAlign: 'center', marginBottom: '32px', opacity: 0.7 }}>Send an invitation link to add a new user to Axiom Corp.</p>
                  
                  <div className="settings-card" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '32px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                      
                      {/* Email */}
                      <div>
                        <label style={{ display: 'block', fontSize: '0.875rem', color: 'rgba(255,255,255,0.7)', marginBottom: '8px' }}>Email Address</label>
                        <input type="email" placeholder="colleague@company.com" style={{ width: '100%', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', padding: '12px', borderRadius: '6px', color: '#f5f4f0', outline: 'none', fontSize: '1rem' }} />
                      </div>

                      <div style={{ display: 'flex', gap: '24px' }}>
                        {/* Role Dropdown */}
                        <div style={{ flex: 1 }}>
                          <label style={{ display: 'block', fontSize: '0.875rem', color: 'rgba(255,255,255,0.7)', marginBottom: '8px' }}>Role</label>
                          <div style={{ position: 'relative' }}>
                            <div 
                              onClick={() => { setRoleDropdownOpen(!roleDropdownOpen); setTeamDropdownOpen(false); }}
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
                                  {['Employee', 'Manager', 'Admin', 'HR'].map(r => (
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

                        {/* Team Dropdown */}
                        <div style={{ flex: 1 }}>
                          <label style={{ display: 'block', fontSize: '0.875rem', color: 'rgba(255,255,255,0.7)', marginBottom: '8px' }}>Assign Team</label>
                          <div style={{ position: 'relative' }}>
                            <div 
                              onClick={() => { setTeamDropdownOpen(!teamDropdownOpen); setRoleDropdownOpen(false); }}
                              style={{ width: '100%', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', padding: '12px', borderRadius: '6px', color: '#f5f4f0', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                            >
                              <span>{selectedTeam}</span>
                              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.5, transform: teamDropdownOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
                                <polyline points="6 9 12 15 18 9"></polyline>
                              </svg>
                            </div>
                            <AnimatePresence>
                              {teamDropdownOpen && (
                                <motion.div 
                                  initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }} transition={{ duration: 0.15 }}
                                  style={{ position: 'absolute', top: '100%', left: 0, right: 0, marginTop: '4px', background: '#1c1c1c', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', overflow: 'hidden', zIndex: 10, boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}
                                >
                                  {['Engineering', 'Marketing', 'HR & Ops', 'Management'].map(t => (
                                    <div 
                                      key={t} 
                                      onClick={() => { setSelectedTeam(t); setTeamDropdownOpen(false); }}
                                      style={{ padding: '12px 16px', cursor: 'pointer', background: selectedTeam === t ? 'rgba(255,255,255,0.05)' : 'transparent', color: selectedTeam === t ? 'var(--soft-lime)' : '#f5f4f0', fontSize: '0.875rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
                                    >
                                      {t}
                                      {selectedTeam === t && <span style={{ color: 'var(--soft-lime)' }}>✓</span>}
                                    </div>
                                  ))}
                                </motion.div>
                              )}
                            </AnimatePresence>
                          </div>
                        </div>
                      </div>

                      {/* Submit */}
                      <div style={{ marginTop: '16px' }}>
                        <button style={{ width: '100%', background: 'var(--soft-lime)', color: '#000', border: 'none', padding: '14px', borderRadius: '6px', fontWeight: 600, fontSize: '1rem', cursor: 'pointer' }}>
                          Send Invitation Link
                        </button>
                      </div>

                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {/* TEAMS TAB */}
            {activeTab === 'teams' && (
              <motion.div key="teams" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                  <h2 className="heading-medium" style={{ fontSize: '1.25rem' }}>Departments & Teams</h2>
                  <button style={{ background: 'transparent', color: '#f5f4f0', border: '1px solid rgba(255,255,255,0.2)', padding: '8px 16px', borderRadius: '4px', fontWeight: 500, fontSize: '0.875rem', cursor: 'pointer' }}>+ Create Team</button>
                </div>
                
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '24px' }}>
                  {TEAMS.map((team, idx) => (
                    <div key={idx} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '24px', transition: 'background 0.2s', cursor: 'pointer' }}>
                      <h3 style={{ fontSize: '1.125rem', fontWeight: 600, color: '#f5f4f0', marginBottom: '16px' }}>{team.name}</h3>
                      <div style={{ display: 'flex', gap: '16px' }}>
                        <div>
                          <p style={{ fontSize: '1.5rem', fontWeight: 800, color: '#f5f4f0' }}>{team.employees}</p>
                          <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase' }}>Employees</p>
                        </div>
                        <div style={{ width: '1px', background: 'rgba(255,255,255,0.1)' }}></div>
                        <div>
                          <p style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--soft-lime)' }}>{team.agents}</p>
                          <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase' }}>Active Agents</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}

            {/* ANALYTICS TAB */}
            {activeTab === 'analytics' && (
              <motion.div key="analytics" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                <h2 className="heading-medium" style={{ fontSize: '1.25rem', marginBottom: '24px' }}>Platform Analytics & ROI</h2>
                
                <div style={{ display: 'flex', gap: '24px', marginBottom: '40px' }}>
                  <div style={{ flex: 1, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '32px' }}>
                    <p style={{ fontSize: '0.875rem', color: 'rgba(255,255,255,0.6)', marginBottom: '8px' }}>Est. Cost Saved (30 Days)</p>
                    <h3 style={{ fontSize: '2.5rem', fontWeight: 800, color: '#f5f4f0' }}>$14,250</h3>
                    <p style={{ fontSize: '0.75rem', color: '#4ade80', marginTop: '8px' }}>+12% from last month</p>
                  </div>
                  <div style={{ flex: 1, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '32px' }}>
                    <p style={{ fontSize: '0.875rem', color: 'rgba(255,255,255,0.6)', marginBottom: '8px' }}>Tokens Processed</p>
                    <h3 style={{ fontSize: '2.5rem', fontWeight: 800, color: '#f5f4f0' }}>8.4M</h3>
                    <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)', marginTop: '8px' }}>Across 42,850 API calls</p>
                  </div>
                  <div style={{ flex: 1, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '32px' }}>
                    <p style={{ fontSize: '0.875rem', color: 'rgba(255,255,255,0.6)', marginBottom: '8px' }}>Active Users</p>
                    <h3 style={{ fontSize: '2.5rem', fontWeight: 800, color: '#f5f4f0' }}>18/20</h3>
                    <p style={{ fontSize: '0.75rem', color: '#4ade80', marginTop: '8px' }}>90% Seat Utilization</p>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
                  {/* PIE CHART SECTION */}
                  <div className="settings-card" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '32px', display: 'flex', flexDirection: 'column' }}>
                    <h3 style={{ fontSize: '1.125rem', fontWeight: 600, color: '#f5f4f0', marginBottom: '8px' }}>Token Usage by Agent</h3>
                    
                    <div style={{ display: 'flex', alignItems: 'center', gap: '40px', flex: 1 }}>
                      {/* Recharts Pie Chart */}
                      <div style={{ width: '200px', height: '200px', position: 'relative' }}>
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={[
                                { name: 'Hiring AI', value: 4500000, color: '#4ade80' },
                                { name: 'Knowledge AI', value: 3500000, color: '#3b82f6' },
                                { name: 'Comms AI', value: 400000, color: '#8b5cf6' }
                              ]}
                              cx="50%"
                              cy="50%"
                              innerRadius={60}
                              outerRadius={80}
                              paddingAngle={5}
                              dataKey="value"
                              stroke="none"
                            >
                              {[
                                { name: 'Hiring AI', value: 4500000, color: '#4ade80' },
                                { name: 'Knowledge AI', value: 3500000, color: '#3b82f6' },
                                { name: 'Comms AI', value: 400000, color: '#8b5cf6' }
                              ].map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={entry.color} />
                              ))}
                            </Pie>
                            <Tooltip 
                              contentStyle={{ background: '#1c1c1c', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#f5f4f0' }}
                              itemStyle={{ color: '#f5f4f0' }}
                              formatter={(value) => `${(value / 1000000).toFixed(1)}M Tokens`}
                            />
                          </PieChart>
                        </ResponsiveContainer>
                        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', pointerEvents: 'none' }}>
                          <span style={{ color: '#f5f4f0', fontSize: '1.25rem', fontWeight: 700 }}>8.4M</span>
                          <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem' }}>Total</span>
                        </div>
                      </div>

                      {/* Legend */}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', flex: 1 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <div style={{ width: '12px', height: '12px', background: '#4ade80', borderRadius: '2px' }}></div>
                            <span style={{ color: '#f5f4f0', fontSize: '0.875rem', fontWeight: 500 }}>Hiring AI</span>
                          </div>
                          <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.875rem' }}>4.5M</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <div style={{ width: '12px', height: '12px', background: '#3b82f6', borderRadius: '2px' }}></div>
                            <span style={{ color: '#f5f4f0', fontSize: '0.875rem', fontWeight: 500 }}>Knowledge AI</span>
                          </div>
                          <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.875rem' }}>3.5M</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <div style={{ width: '12px', height: '12px', background: '#8b5cf6', borderRadius: '2px' }}></div>
                            <span style={{ color: '#f5f4f0', fontSize: '0.875rem', fontWeight: 500 }}>Comms AI</span>
                          </div>
                          <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.875rem' }}>400K</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* ACTIVITY LOG SECTION */}
                  <div className="settings-card" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '32px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                      <h3 style={{ fontSize: '1.125rem', fontWeight: 600, color: '#f5f4f0' }}>Recent Activity</h3>
                      <button style={{ background: 'transparent', color: 'var(--soft-lime)', border: 'none', cursor: 'pointer', fontSize: '0.875rem' }}>View All</button>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                      {[
                        { title: 'Marcus generated a hiring report', time: '10 mins ago', type: 'Hiring AI' },
                        { title: 'Sarah updated company policies', time: '1 hour ago', type: 'Knowledge AI' },
                        { title: 'Alex drafted 5 marketing emails', time: '3 hours ago', type: 'Comms AI' },
                        { title: 'Priya invited to Marketing Team', time: 'Yesterday', type: 'System' }
                      ].map((log, i) => (
                        <div key={i} style={{ display: 'flex', gap: '16px', alignItems: 'flex-start', paddingBottom: '16px', borderBottom: i === 3 ? 'none' : '1px solid rgba(255,255,255,0.05)' }}>
                          <div style={{ width: '8px', height: '8px', background: log.type === 'Hiring AI' ? 'var(--soft-lime)' : log.type === 'Knowledge AI' ? '#3b82f6' : log.type === 'Comms AI' ? '#8b5cf6' : '#888', borderRadius: '50%', marginTop: '6px' }}></div>
                          <div>
                            <p style={{ color: '#f5f4f0', fontSize: '0.875rem', marginBottom: '4px', fontWeight: 500 }}>{log.title}</p>
                            <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.75rem' }}>{log.time} • {log.type}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

              </motion.div>
            )}

          </AnimatePresence>
        </motion.div>
      </main>
    </div>
  );
}
