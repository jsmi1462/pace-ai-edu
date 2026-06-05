import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import axios from 'axios';

const formatDate = (dateStr) => {
  if (!dateStr) return null;
  return new Date(dateStr).toLocaleDateString('en-US', { year: 'numeric', month: 'long' });
};

const formatRunDate = (dateStr) => {
  if (!dateStr) return '';
  // Parse as local date (YYYY-MM-DD) to avoid UTC offset shifting the day
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
};

const parseSteps = (raw) => {
  try { return JSON.parse(raw || '[]'); } catch { return []; }
};

const decodeEntities = (str) => {
  if (!str) return str;
  const txt = document.createElement('textarea');
  txt.innerHTML = str;
  return txt.value;
};

// ── Hierarchical date navigator ───────────────────────────────────────────────
// Current month → individual dates
// Older months  → collapsed to "Month Year", expand on click
// Older years   → collapsed to "Year", expand on click
const DateNav = ({ dates, currentDate, onSelect }) => {
  const [expandedYears, setExpandedYears] = useState({});
  const [expandedMonths, setExpandedMonths] = useState({});

  const pastDates = dates.slice(1); // exclude the latest (already shown)
  if (pastDates.length === 0) return null;

  const latestYM  = dates[0]?.substring(0, 7) ?? ''; // "YYYY-MM"
  const latestYear = dates[0]?.substring(0, 4) ?? ''; // "YYYY"

  // Group: { "2026": { "2026-06": ["2026-06-04", ...], "2026-05": [...] } }
  const groups = {};
  for (const d of pastDates) {
    const yr = d.substring(0, 4);
    const ym = d.substring(0, 7);
    if (!groups[yr]) groups[yr] = {};
    if (!groups[yr][ym]) groups[yr][ym] = [];
    groups[yr][ym].push(d);
  }

  const fmtMonth = (ym) => {
    const [y, m] = ym.split('-').map(Number);
    return new Date(y, m - 1, 1).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  };
  const fmtDay = (d) => {
    const [y, m, day] = d.split('-').map(Number);
    return new Date(y, m - 1, day).toLocaleDateString('en-US', { month: 'long', day: 'numeric' });
  };

  const toggleYear  = (yr) => setExpandedYears(e  => ({ ...e, [yr]: !e[yr] }));
  const toggleMonth = (ym) => setExpandedMonths(e => ({ ...e, [ym]: !e[ym] }));

  return (
    <div className="digest-past-dropdown">
      {Object.keys(groups).sort((a, b) => b - a).map(yr => {
        const isCurrentYear = yr === latestYear;
        const yearOpen = isCurrentYear || !!expandedYears[yr];
        const months = Object.keys(groups[yr]).sort((a, b) => b.localeCompare(a));

        return (
          <div key={yr} className="digest-nav-group">
            {!isCurrentYear && (
              <button className="digest-nav-year-btn" onClick={() => toggleYear(yr)}>
                <span>{yr}</span>
                <span className="digest-nav-chevron">{yearOpen ? '▾' : '▸'}</span>
              </button>
            )}
            {yearOpen && months.map(ym => {
              const isCurrentMonth = ym === latestYM;
              const monthOpen = isCurrentMonth || !!expandedMonths[ym];
              const mDates = groups[yr][ym];

              if (isCurrentMonth) {
                return mDates.map(d => (
                  <button
                    key={d}
                    className={`digest-past-item ${d === currentDate ? 'digest-past-item-active' : ''}`}
                    onClick={() => onSelect(d)}
                  >
                    {fmtDay(d)}
                  </button>
                ));
              }

              return (
                <div key={ym}>
                  <button className="digest-nav-month-btn" onClick={() => toggleMonth(ym)}>
                    <span>{fmtMonth(ym)}</span>
                    <span className="digest-nav-chevron">{monthOpen ? '▾' : '▸'}</span>
                  </button>
                  {monthOpen && mDates.map(d => (
                    <button
                      key={d}
                      className={`digest-past-item digest-past-item-sub ${d === currentDate ? 'digest-past-item-active' : ''}`}
                      onClick={() => onSelect(d)}
                    >
                      {fmtDay(d)}
                    </button>
                  ))}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
};

const POLL_INTERVAL = 12000;
const POLL_TIMEOUT = 15 * 60 * 1000;

const RATINGS = [
  { value: 'awesome',    label: 'Excellent' },
  { value: 'good',       label: 'Good'      },
  { value: 'bad',        label: 'Bad'       },
  { value: 'irrelevant', label: 'Irrelevant'},
];

const RatingBar = ({ articleId, initial }) => {
  const [current, setCurrent] = useState(initial || null);
  const [saving, setSaving] = useState(false);

  const rate = async (value) => {
    const next = current === value ? null : value; // tap again to clear
    setSaving(true);
    try {
      await axios.post('/api/digest/rate', { article_id: articleId, rating: next });
      setCurrent(next);
    } catch (e) {
      console.error('Rating failed', e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rating-bar">
      <span className="rating-label">Rate this</span>
      {RATINGS.map(r => (
        <button
          key={r.value}
          className={`rating-btn rating-btn-${r.value} ${current === r.value ? 'rating-btn-active' : ''}`}
          onClick={() => rate(r.value)}
          disabled={saving}
          title={current === r.value ? 'Click to clear' : r.label}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
};

const Digest = () => {
  const [articles, setArticles] = useState([]);
  const [fresh, setFresh] = useState(true);
  const [hasProfile, setHasProfile] = useState(true);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [noMatches, setNoMatches] = useState(false);
  const [progress, setProgress] = useState({ evaluated: 0, total: 50 });
  const [timeRemaining, setTimeRemaining] = useState(null);
  const [dates, setDates] = useState([]);
  const [currentDate, setCurrentDate] = useState(null);
  const [pastOpen, setPastOpen] = useState(false);
  const pollRef = useRef(null);
  const pollStartRef = useRef(null);
  const progressRef = useRef(null);
  const startTimeRef = useRef(null);
  const baselineRef = useRef(0);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const startGenerating = searchParams.get('generating') === 'true';
    if (startGenerating) {
      navigate('/', { replace: true });
      setLoading(false);
      setRegenerating(true);
      startTimeRef.current = Date.now();
      baselineRef.current = 0;
      pollForResults();
    } else {
      fetchDigest();
    }
    return () => stopPolling();
  }, []);

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (progressRef.current) { clearInterval(progressRef.current); progressRef.current = null; }
  };

  const startProgressPolling = () => {
    progressRef.current = setInterval(async () => {
      try {
        const res = await axios.get('/api/digest/progress');
        const { evaluated, total } = res.data;
        const net = Math.max(0, evaluated - baselineRef.current);
        setProgress({ evaluated: net, total });

        const elapsed = (Date.now() - startTimeRef.current) / 1000;
        if (net >= 3 && elapsed >= 15) {
          const rate = net / elapsed;
          const remaining = Math.ceil((total - net) / rate / 60);
          setTimeRemaining(Math.max(0, remaining));
        }

        checkComplete(net, total);
      } catch { /* silent */ }
    }, 8000);
  };

  const checkComplete = (evaluated, total) => {
    if (evaluated >= total && total > 0) {
      axios.get('/api/digest/me').then(res => {
        if (res.data.articles.length > 0) {
          const { articles, fresh, dates, currentDate } = res.data;
          setArticles(articles);
          setFresh(fresh);
          setDates(dates || []);
          setCurrentDate(currentDate || null);
          stopPolling();
          setRegenerating(false);
        } else {
          stopPolling();
          setRegenerating(false);
          setNoMatches(true);
        }
      }).catch(() => {
        stopPolling();
        setRegenerating(false);
        setNoMatches(true);
      });
    }
  };

  const fetchDigest = async (date = null) => {
    setLoading(true);
    try {
      const url = date ? `/api/digest/me?date=${date}` : '/api/digest/me';
      const [digestRes, profileRes] = await Promise.allSettled([
        axios.get(url),
        axios.get('/api/profile'),
      ]);
      if (digestRes.status === 'fulfilled') {
        const { articles, fresh, dates, currentDate } = digestRes.value.data;
        setArticles(articles);
        setFresh(fresh);
        setDates(dates || []);
        setCurrentDate(currentDate || null);
      }
      setHasProfile(profileRes.status === 'fulfilled');
    } catch (err) {
      console.error('Error fetching digest:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadDate = (date) => {
    setPastOpen(false);
    fetchDigest(date);
  };

  const pollForResults = () => {
    setProgress({ evaluated: 0, total: 50 });
    setTimeRemaining(null);
    startProgressPolling();
    pollStartRef.current = Date.now();
    pollRef.current = setInterval(async () => {
      if (Date.now() - pollStartRef.current > POLL_TIMEOUT) {
        stopPolling();
        setRegenerating(false);
        return;
      }
      try {
        const res = await axios.get('/api/digest/me');
        if (res.data.articles.length > 0) {
          const { articles, fresh, dates, currentDate } = res.data;
          setArticles(articles);
          setFresh(fresh);
          setDates(dates || []);
          setCurrentDate(currentDate || null);
          setHasProfile(true);
          stopPolling();
          setRegenerating(false);
        }
      } catch (err) {
        console.error('Poll error:', err);
      }
    }, POLL_INTERVAL);
  };

  const handleRegenerate = async () => {
    setRegenerating(true);
    setNoMatches(false);
    setArticles([]);
    startTimeRef.current = Date.now();

    try {
      const prog = await axios.get('/api/digest/progress');
      baselineRef.current = prog.data.evaluated;
    } catch {
      baselineRef.current = 0;
    }

    try {
      await axios.post('/api/digest/regenerate');
      pollForResults();
    } catch (err) {
      console.error('Error regenerating digest:', err);
      setRegenerating(false);
    }
  };

  if (loading) return (
    <div className="page-content">
      <p className="loading">Gathering your digest…</p>
    </div>
  );

  return (
    <div className="page-content">
      <div className="digest-header">
        <div>
          <h1 className="digest-title">This Week's Reading</h1>
          <p className="digest-subtitle">
            {currentDate ? formatRunDate(currentDate) : 'Research matched to your classroom, ready to use.'}
          </p>
        </div>
        <div className="digest-header-actions">
          {dates.length > 1 && (
            <div className="digest-past-wrapper">
              <button className="btn-past-issues" onClick={() => setPastOpen(o => !o)}>
                Past issues {pastOpen ? '▲' : '▼'}
              </button>
              {pastOpen && (
                <DateNav dates={dates} currentDate={currentDate} onSelect={loadDate} />
              )}
            </div>
          )}
          {currentDate && currentDate !== dates[0] && (
            <button className="btn-past-issues" onClick={() => loadDate(null)}>
              ← Latest
            </button>
          )}
          <button className="btn-refresh" onClick={handleRegenerate} disabled={regenerating}>
            {regenerating ? 'Generating…' : 'Refresh'}
          </button>
        </div>
      </div>

      {regenerating ? (
        <div className="generating-state">
          <p className="generating-headline">Finding your articles…</p>
          <p className="generating-subtext">We're reading through recent research and matching it to your classroom. This page will update automatically when your digest is ready.</p>
          <div className="progress-bar-track">
            <div
              className="progress-bar-fill"
              style={{ width: `${Math.min(95, Math.round((progress.evaluated / progress.total) * 100))}%` }}
            />
          </div>
          <div className="progress-footer">
            <p className="progress-label">
              {progress.evaluated === 0
                ? 'Starting up…'
                : `${progress.evaluated} of ~${progress.total} articles evaluated`}
            </p>
            <p className="progress-time">
              {timeRemaining === null ? 'Estimating…'
                : timeRemaining <= 0 ? 'Almost done…'
                : timeRemaining === 1 ? '~1 min remaining'
                : `~${timeRemaining} min remaining`}
            </p>
          </div>
        </div>
      ) : !hasProfile ? (
        <div className="welcome-state">
          <h2 className="welcome-headline">Your weekly research digest, matched to your classroom.</h2>
          <p className="welcome-body">Every week, Pace Edu finds peer-reviewed research relevant to what you're teaching and translates it into plain-language summaries and ready-to-use action steps. Takes 2 minutes to set up.</p>
          <Link to="/profile?onboarding=true" className="btn-start">Get started →</Link>
        </div>
      ) : noMatches ? (
        <div className="empty-state">
          No new research matched your profile this run — check back after next Monday's update, or click Refresh to try again.
        </div>
      ) : articles.length === 0 ? (
        <div className="welcome-state">
          <h2 className="welcome-headline">Ready to find your articles.</h2>
          <p className="welcome-body">We'll scan recent research and find articles matched to your classroom. Takes about 5–10 minutes.</p>
          <button className="btn-start" onClick={handleRegenerate}>Generate my digest →</button>
        </div>
      ) : (
      <>
        {!fresh && (
          <div className="caught-up-banner">
            You're all caught up — new articles arrive each Monday. Here's last week's reading in the meantime.
          </div>
        )}
        <div className="article-list">
          {articles.map((article, index) => {
            const steps = parseSteps(article.action_steps);
            const meta = [article.authors, formatDate(article.publication_date)].filter(Boolean).join(' · ');
            return (
              <article key={index} className="article">
                <div className="article-eyebrow">
                  <span className="article-number">{String(index + 1).padStart(2, '0')}</span>
                  {article.source && <span className="article-source">{article.source}</span>}
                </div>

                <h2 className="article-title">
                  {article.url
                    ? <a href={article.url} target="_blank" rel="noopener noreferrer">{decodeEntities(article.title)}</a>
                    : decodeEntities(article.title)}
                </h2>

                {meta && <p className="article-meta">{decodeEntities(meta)}</p>}

                <p className="article-summary">{article.summary}</p>

                {steps.length > 0 && (
                  <>
                    <p className="article-steps-label">Try tomorrow</p>
                    <ol className="article-steps">
                      {steps.map((step, i) => <li key={i}>{step}</li>)}
                    </ol>
                  </>
                )}

                {article.mission_alignment && (
                  <p className="article-connection">
                    <strong>Pace connection — </strong>{article.mission_alignment}
                  </p>
                )}

                <RatingBar articleId={article.article_id} initial={article.user_rating} />
              </article>
            );
          })}
        </div>
      </>
      )}
    </div>
  );
};

export default Digest;
