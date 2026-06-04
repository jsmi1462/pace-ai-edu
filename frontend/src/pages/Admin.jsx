import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const fmt = (d) => {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

const fmtTime = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit' });
};

const fmtDuration = (startIso, endIso) => {
  if (!startIso || !endIso) return '—';
  const ms = new Date(endIso) - new Date(startIso);
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
};

const fmtElapsed = (startIso) => {
  if (!startIso) return null;
  const s = Math.floor((Date.now() - new Date(startIso)) / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
};

// Parse log lines to derive current phase + teacher progress
const parsePipelineProgress = (logLines, totalTeachers) => {
  if (!logLines || logLines.length === 0) return { phase: 'Starting…', teachersDone: 0 };

  let phase = 'Starting…';
  let teachersDone = 0;
  let teachersStarted = 0;

  for (const { line } of logLines) {
    if (line.includes('Embedding probe OK'))          phase = 'Probe OK — fetching RSS…';
    if (line.includes('Fetching RSS'))                phase = 'Fetching RSS feeds…';
    if (line.includes('Total RSS articles fetched'))  phase = 'RSS done — fetching ERIC…';
    if (line.includes('ERIC fetching'))               phase = 'Fetching ERIC (slow)…';
    if (line.includes('Ingestion phase 1'))           phase = 'Ingesting articles…';
    if (line.includes('Ingestion phase 2'))           phase = 'Embedding articles…';
    if (line.includes('Ingestion phase 3'))           phase = 'Tagging disciplines…';
    if (line.includes('Processing teacher:'))         { phase = 'Evaluating teachers…'; teachersStarted++; }
    if (line.includes('Yes articles this run'))       teachersDone++;
    if (line.includes('Cleanup:'))                    phase = 'Cleanup pass…';
    if (line.includes('Pipeline finished'))           phase = 'Done';
  }

  return { phase, teachersDone, teachersStarted };
};

const POLL_FAST = 2000;
const POLL_SLOW = 10000;

const Admin = () => {
  const [users, setUsers] = useState([]);
  const [articles, setArticles] = useState(null);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);

  // Pipeline live state (from polling)
  const [pipelineStatus, setPipelineStatus] = useState({ runAllActive: false, running: [], logs: {}, history: [] });
  const [logTab, setLogTab] = useState('__all__');
  const [logsOpen, setLogsOpen] = useState(true);
  const [elapsed, setElapsed] = useState(null);
  const terminalRef = useRef(null);
  const logSectionRef = useRef(null);
  const elapsedTimer = useRef(null);
  const pollTimer = useRef(null);

  const navigate = useNavigate();

  const anyRunning = pipelineStatus.runAllActive || pipelineStatus.running.length > 0;

  const loadData = useCallback(async () => {
    try {
      const [u, a] = await Promise.all([
        axios.get('/api/admin/users'),
        axios.get('/api/admin/articles'),
      ]);
      setUsers(u.data);
      setArticles(a.data);
    } catch (err) {
      if (err.response?.status === 403) setForbidden(true);
    } finally {
      setLoading(false);
    }
  }, []);

  const pollStatus = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/admin/pipeline-status');
      setPipelineStatus(data);
      // Reload DB stats after a run completes (running→idle transition)
      if (!data.runAllActive && data.running.length === 0) {
        loadData();
      }
    } catch (_) {}
  }, [loadData]);

  // Kick off initial data load
  useEffect(() => { loadData(); }, [loadData]);

  // Polling loop — fast when busy, slow when idle
  useEffect(() => {
    const tick = async () => {
      await pollStatus();
      const delay = anyRunning ? POLL_FAST : POLL_SLOW;
      pollTimer.current = setTimeout(tick, delay);
    };
    tick();
    return () => clearTimeout(pollTimer.current);
  }, [pollStatus, anyRunning]);

  // Live elapsed timer — ticks every second while running
  useEffect(() => {
    clearInterval(elapsedTimer.current);
    if (anyRunning) {
      const startKey = runAllActive ? '__all__' : (running[0] || null);
      const startIso = pipelineStatus.startTimes?.[startKey];
      elapsedTimer.current = setInterval(() => setElapsed(fmtElapsed(startIso)), 1000);
      setElapsed(fmtElapsed(startIso));
    } else {
      setElapsed(null);
    }
    return () => clearInterval(elapsedTimer.current);
  }, [anyRunning, runAllActive, running, pipelineStatus.startTimes]);

  // Scroll within the terminal box only — never touch page scroll
  useEffect(() => {
    if (logsOpen && anyRunning && terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [pipelineStatus.logs, logTab, logsOpen, anyRunning]);

  // Auto-open log panel when pipeline starts
  useEffect(() => {
    if (anyRunning) setLogsOpen(true);
  }, [anyRunning]);

  const runPipeline = async (email) => {
    try {
      await axios.post(`/api/admin/regenerate/${encodeURIComponent(email)}`);
      setLogTab(email);
      await pollStatus();
    } catch (err) {
      alert(err.response?.data?.error || 'Failed to start pipeline');
    }
  };

  const runAll = async () => {
    try {
      await axios.post('/api/admin/run-all');
      setLogTab('__all__');
      await pollStatus();
    } catch (err) {
      alert(err.response?.data?.error || 'Failed to start pipeline');
    }
  };

  const cancelPipeline = async (key) => {
    try {
      await axios.post(`/api/admin/cancel/${encodeURIComponent(key === '__all__' ? 'all' : key)}`);
      await pollStatus();
    } catch (err) {
      alert(err.response?.data?.error || 'Failed to cancel');
    }
  };

  const impersonate = (email) => {
    localStorage.setItem('impersonating', email);
    window.dispatchEvent(new CustomEvent('impersonation-change'));
    navigate('/');
  };

  if (loading) return <div className="page-content"><p className="loading">Loading…</p></div>;
  if (forbidden) return <div className="page-content"><p className="loading">Access restricted.</p></div>;

  const { running, runAllActive, logs, history } = pipelineStatus;
  const isTeacherRunning = (email) => runAllActive || running.includes(email);

  // Build log tab list
  const logKeys = ['__all__', ...Object.keys(logs).filter(k => k !== '__all__')];
  const currentLogs = logs[logTab] || [];

  return (
    <div className="page-content admin-content">
      <div className="admin-header">
        <div className="admin-header-top">
          <div>
            <h1 className="admin-title">Admin</h1>
            <p className="admin-subtitle">Pace Edu internal tools — eye in the sky.</p>
          </div>
          <div className="admin-live-indicator">
            <span className={`admin-pulse ${anyRunning ? 'admin-pulse-active' : ''}`} />
            <span className="admin-live-label">{anyRunning ? 'Pipeline running' : 'Idle'}</span>
          </div>
        </div>
      </div>

      {/* ── System Stats Bar ── */}
      {articles && (
        <section className="admin-section admin-statsbar-section">
          <div className="admin-statsbar">
            <div className="admin-statcell">
              <span className="admin-statcell-value">{articles.active_teachers ?? '—'}</span>
              <span className="admin-statcell-label">Active Teachers</span>
            </div>
            <div className="admin-statcell">
              <span className="admin-statcell-value">{articles.total?.toLocaleString() ?? '—'}</span>
              <span className="admin-statcell-label">Total Articles</span>
            </div>
            <div className="admin-statcell">
              <span className="admin-statcell-value">{articles.ingested_today?.toLocaleString() ?? '—'}</span>
              <span className="admin-statcell-label">Ingested Today</span>
            </div>
            <div className="admin-statcell">
              <span className="admin-statcell-value">{articles.matched?.toLocaleString() ?? '—'}</span>
              <span className="admin-statcell-label">Total Matched</span>
            </div>
            <div className="admin-statcell">
              <span className="admin-statcell-value">{articles.rejected?.toLocaleString() ?? '—'}</span>
              <span className="admin-statcell-label">Total Rejected</span>
            </div>
            <div className="admin-statcell">
              <span className={`admin-statcell-value ${articles.errors > 0 ? 'admin-statcell-error' : ''}`}>
                {articles.errors ?? '—'}
              </span>
              <span className="admin-statcell-label">Errors</span>
            </div>
            <div className="admin-statcell">
              <span className="admin-statcell-value">
                {articles.match_rate != null ? `${articles.match_rate}%` : '—'}
              </span>
              <span className="admin-statcell-label">Match Rate</span>
            </div>
            <div className="admin-statcell">
              <span className="admin-statcell-value">{articles.today_matched ?? '—'}</span>
              <span className="admin-statcell-label">Matched Today</span>
            </div>
            <div className="admin-statcell">
              <span className="admin-statcell-value">{articles.today?.toLocaleString() ?? '—'}</span>
              <span className="admin-statcell-label">Evaluated Today</span>
            </div>
          </div>
        </section>
      )}

      {/* ── Teachers ── */}
      <section className="admin-section">
        <div className="admin-section-header">
          <h2 className="admin-section-title">
            Teachers
            {running.length > 0 && (
              <span className="admin-section-running"> — {running.length} running</span>
            )}
          </h2>
          <div className="admin-run-controls">
            {runAllActive && (
              <button className="btn-admin-cancel" onClick={() => cancelPipeline('__all__')}>
                Cancel All ✕
              </button>
            )}
            <button className="btn-admin-run" onClick={runAll} disabled={runAllActive}>
              {runAllActive ? 'Running…' : 'Run all ↺'}
            </button>
          </div>
        </div>
        <table className="admin-table">
          <thead>
            <tr>
              <th></th>
              <th>Name</th>
              <th>Email</th>
              <th>Discipline</th>
              <th>Yrs</th>
              <th>Pending</th>
              <th>Sent</th>
              <th>Matched</th>
              <th>Rejected</th>
              <th>Rate</th>
              <th>Today</th>
              <th>Last Run</th>
              <th></th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {users.length === 0 && (
              <tr><td colSpan={14} className="admin-empty">No faculty profiles yet.</td></tr>
            )}
            {users.map(u => {
              const isRunning = isTeacherRunning(u.email);
              return (
                <tr key={u.email} className={isRunning ? 'admin-row-running' : ''}>
                  <td className="admin-status-cell">
                    {isRunning
                      ? <span className="admin-row-spinner" title="Pipeline running" />
                      : <span className={`admin-row-dot ${u.is_active ? 'admin-row-dot-active' : ''}`} title={u.is_active ? 'Active' : 'Inactive'} />
                    }
                  </td>
                  <td>{u.first_name} {u.last_name}</td>
                  <td className="admin-email">{u.email}</td>
                  <td className="admin-cell-small">{u.discipline || '—'}</td>
                  <td className="admin-cell-num">{u.years_experience ?? '—'}</td>
                  <td>
                    <span className={u.pending > 0 ? 'admin-badge admin-badge-active' : 'admin-badge'}>
                      {u.pending}
                    </span>
                  </td>
                  <td className="admin-cell-num">{u.sent}</td>
                  <td className="admin-cell-num">{u.total_matched}</td>
                  <td className="admin-cell-num">{u.total_rejected}</td>
                  <td className="admin-cell-num">
                    {u.match_rate != null
                      ? <span className={`admin-rate ${u.match_rate >= 50 ? 'admin-rate-good' : u.match_rate < 25 ? 'admin-rate-low' : ''}`}>{u.match_rate}%</span>
                      : '—'}
                  </td>
                  <td className="admin-cell-num">
                    {u.today_matches > 0
                      ? <span className="admin-today-badge">{u.today_matches} new</span>
                      : <span className="admin-cell-dim">{u.today_evaluated > 0 ? `${u.today_evaluated} eval` : '—'}</span>
                    }
                  </td>
                  <td className="admin-cell-small">{fmt(u.last_evaluated)}</td>
                  <td>
                    {isRunning ? (
                      <button
                        className="btn-cancel-single"
                        onClick={() => cancelPipeline(u.email)}
                        title={`Cancel pipeline for ${u.email}`}
                      >
                        ✕
                      </button>
                    ) : (
                      <button
                        className="btn-run-single"
                        onClick={() => runPipeline(u.email)}
                        disabled={runAllActive}
                        title={`Run pipeline for ${u.email}`}
                      >
                        ↺
                      </button>
                    )}
                  </td>
                  <td>
                    <button
                      className="btn-view-as"
                      onClick={() => impersonate(u.email)}
                      disabled={isRunning}
                      title={`View digest as ${u.email}`}
                    >
                      View as →
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      {/* ── Live Log Panel ── */}
      <section className="admin-section admin-log-section" ref={logSectionRef}>
        <div className="admin-section-header">
          <h2 className="admin-section-title">
            Pipeline Log
            {anyRunning && <span className="admin-log-live-badge">LIVE</span>}
          </h2>
          <div className="admin-log-header-right">
            {anyRunning && (() => {
              const activeLogs = currentLogs;
              const { phase, teachersDone, teachersStarted } = parsePipelineProgress(activeLogs, users.length);
              const teacherInfo = teachersStarted > 0
                ? ` — ${teachersDone}/${users.length} teachers`
                : '';
              return (
                <span className="admin-pipeline-status">
                  <span className="admin-pipeline-phase">{phase}{teacherInfo}</span>
                  {elapsed && <span className="admin-pipeline-elapsed">{elapsed}</span>}
                </span>
              );
            })()}
            <button className="btn-admin-toggle" onClick={() => setLogsOpen(o => !o)}>
              {logsOpen ? 'Collapse ▲' : 'Expand ▼'}
            </button>
          </div>
        </div>

        {logsOpen && (
          <div className="admin-terminal-wrap">
            <div className="admin-log-tabs">
              {logKeys.map(key => (
                <button
                  key={key}
                  className={`admin-log-tab ${logTab === key ? 'admin-log-tab-active' : ''}`}
                  onClick={() => setLogTab(key)}
                >
                  {key === '__all__' ? 'Global' : key.split('@')[0]}
                  {(key === '__all__' ? runAllActive : running.includes(key)) && (
                    <span className="admin-tab-dot" />
                  )}
                </button>
              ))}
            </div>
            <div className="admin-terminal" ref={terminalRef}>
              {currentLogs.length === 0 ? (
                <div className="admin-terminal-empty">No log output yet.</div>
              ) : (
                currentLogs.map((entry, i) => (
                  <div
                    key={i}
                    className={`admin-log-line ${entry.stream === 'stderr' ? 'admin-log-stderr' : ''}`}
                  >
                    <span className="admin-log-ts">{fmtTime(entry.ts)}</span>
                    <span className="admin-log-text">{entry.line}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </section>

      {/* ── Run History ── */}
      {history.length > 0 && (
        <section className="admin-section">
          <h2 className="admin-section-title">Run History</h2>
          <table className="admin-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Target</th>
                <th>Started</th>
                <th>Duration</th>
                <th>Exit</th>
              </tr>
            </thead>
            <tbody>
              {history.slice(0, 20).map((run, i) => (
                <tr key={i}>
                  <td>{run.type === 'all' ? 'Full run' : 'Single'}</td>
                  <td className="admin-email">{run.target || 'all teachers'}</td>
                  <td className="admin-cell-small">{fmtTime(run.startedAt)}</td>
                  <td className="admin-cell-num">{fmtDuration(run.startedAt, run.endedAt)}</td>
                  <td>
                    <span className={`admin-exit-code ${run.exitCode === 0 ? 'admin-exit-ok' : 'admin-exit-err'}`}>
                      {run.exitCode === null ? 'running' : run.exitCode === 0 ? 'ok' : `exit ${run.exitCode}`}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* ── Article Stats ── */}
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
              <span className="admin-stat-value">{articles.ingested_today?.toLocaleString() ?? '—'}</span>
              <span className="admin-stat-label">Ingested Today</span>
            </div>
            <div className="admin-stat">
              <span className="admin-stat-value">{articles.today?.toLocaleString() ?? '—'}</span>
              <span className="admin-stat-label">Evaluated Today</span>
            </div>
          </div>

          {articles.sources?.length > 0 && (
            <div className="admin-sources">
              <h3 className="admin-sources-title">By Source</h3>
              <div className="admin-sources-list">
                {articles.sources.map(s => (
                  <div key={s.source} className="admin-source-row">
                    <span className="admin-source-name">{s.source || 'Unknown'}</span>
                    <span className="admin-source-bar-wrap">
                      <span
                        className="admin-source-bar"
                        style={{ width: `${Math.round((s.count / articles.total) * 100)}%` }}
                      />
                    </span>
                    <span className="admin-source-count">{s.count.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {articles.trend?.length > 0 && (
            <div className="admin-trend">
              <h3 className="admin-sources-title">7-Day Ingestion</h3>
              <div className="admin-trend-bars">
                {articles.trend.map(d => {
                  const max = Math.max(...articles.trend.map(t => t.count), 1);
                  const pct = Math.round((d.count / max) * 100);
                  const label = new Date(d.day).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                  return (
                    <div key={d.day} className="admin-trend-col">
                      <span className="admin-trend-count">{d.count > 0 ? d.count : ''}</span>
                      <span className="admin-trend-bar" style={{ height: `${Math.max(pct, 2)}%` }} />
                      <span className="admin-trend-label">{label}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
};

export default Admin;
