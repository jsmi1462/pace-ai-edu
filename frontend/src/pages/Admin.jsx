import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const fmt = (d) => {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

const Admin = () => {
  const [users, setUsers] = useState([]);
  const [articles, setArticles] = useState(null);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [running, setRunning] = useState({});
  const [runningAll, setRunningAll] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([
      axios.get('/api/admin/users'),
      axios.get('/api/admin/articles'),
    ]).then(([u, a]) => {
      setUsers(u.data);
      setArticles(a.data);
    }).catch((err) => {
      if (err.response?.status === 403) setForbidden(true);
    }).finally(() => setLoading(false));
  }, []);

  const runPipeline = async (email) => {
    setRunning(r => ({ ...r, [email]: true }));
    try {
      await axios.post(`/api/admin/regenerate/${encodeURIComponent(email)}`);
    } finally {
      setRunning(r => ({ ...r, [email]: false }));
    }
  };

  const impersonate = (email) => {
    localStorage.setItem('impersonating', email);
    window.dispatchEvent(new CustomEvent('impersonation-change'));
    navigate('/');
  };

  const runAll = async () => {
    setRunningAll(true);
    await Promise.all(users.map(u => runPipeline(u.email)));
    setRunningAll(false);
  };

  if (loading) return <div className="page-content"><p className="loading">Loading…</p></div>;
  if (forbidden) return <div className="page-content"><p className="loading">Access restricted.</p></div>;

  return (
    <div className="page-content admin-content">
      <div className="admin-header">
        <h1 className="admin-title">Admin</h1>
        <p className="admin-subtitle">Pace Edu internal tools.</p>
      </div>

      <section className="admin-section">
        <div className="admin-section-header">
          <h2 className="admin-section-title">Teachers</h2>
          <button className="btn-admin-run" onClick={runAll} disabled={runningAll}>
            {runningAll ? 'Running…' : 'Run all ↺'}
          </button>
        </div>
        <table className="admin-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Discipline</th>
              <th>Grade Band</th>
              <th>Pending</th>
              <th>Sent</th>
              <th>Last Run</th>
              <th></th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {users.length === 0 && (
              <tr><td colSpan={8} className="admin-empty">No faculty profiles yet.</td></tr>
            )}
            {users.map(u => (
              <tr key={u.email}>
                <td>{u.first_name} {u.last_name}</td>
                <td className="admin-email">{u.email}</td>
                <td>{u.discipline || '—'}</td>
                <td>{u.grade_band || '—'}</td>
                <td>
                  <span className={u.pending > 0 ? 'admin-badge admin-badge-active' : 'admin-badge'}>
                    {u.pending}
                  </span>
                </td>
                <td>{u.sent}</td>
                <td>{fmt(u.last_evaluated)}</td>
                <td>
                  <button
                    className="btn-run-single"
                    onClick={() => runPipeline(u.email)}
                    disabled={running[u.email]}
                    title={`Run pipeline for ${u.email}`}
                  >
                    {running[u.email] ? '…' : '↺'}
                  </button>
                </td>
                <td>
                  <button
                    className="btn-view-as"
                    onClick={() => impersonate(u.email)}
                    title={`View digest as ${u.email}`}
                  >
                    View as →
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {articles && (
        <section className="admin-section">
          <h2 className="admin-section-title">Articles</h2>
          <div className="admin-stats">
            <div className="admin-stat">
              <span className="admin-stat-value">{articles.total?.toLocaleString() ?? '—'}</span>
              <span className="admin-stat-label">Total</span>
            </div>
            <div className="admin-stat">
              <span className="admin-stat-value">{articles.matched?.toLocaleString() ?? '—'}</span>
              <span className="admin-stat-label">Matched</span>
            </div>
            <div className="admin-stat">
              <span className="admin-stat-value">{articles.rejected?.toLocaleString() ?? '—'}</span>
              <span className="admin-stat-label">Rejected</span>
            </div>
            <div className="admin-stat">
              <span className="admin-stat-value">{articles.today?.toLocaleString() ?? '—'}</span>
              <span className="admin-stat-label">Evaluated Today</span>
            </div>
          </div>
        </section>
      )}
    </div>
  );
};

export default Admin;
