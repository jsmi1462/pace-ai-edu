import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import axios from 'axios';

const formatDate = (dateStr) => {
  if (!dateStr) return null;
  return new Date(dateStr).toLocaleDateString('en-US', { year: 'numeric', month: 'long' });
};

const parseSteps = (raw) => {
  try { return JSON.parse(raw || '[]'); } catch { return []; }
};

const POLL_INTERVAL = 12000;
const POLL_TIMEOUT = 15 * 60 * 1000;

const Digest = () => {
  const [articles, setArticles] = useState([]);
  const [fresh, setFresh] = useState(true);
  const [hasProfile, setHasProfile] = useState(true);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [progress, setProgress] = useState({ evaluated: 0, total: 50 });
  const pollRef = useRef(null);
  const pollStartRef = useRef(null);
  const progressRef = useRef(null);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const startGenerating = searchParams.get('generating') === 'true';
    if (startGenerating) {
      navigate('/', { replace: true });
      setLoading(false);
      setRegenerating(true);
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
        setProgress(res.data);
      } catch (err) { /* silent */ }
    }, 8000);
  };

  const fetchDigest = async () => {
    setLoading(true);
    try {
      const [digestRes, profileRes] = await Promise.allSettled([
        axios.get('/api/digest/me'),
        axios.get('/api/profile'),
      ]);
      if (digestRes.status === 'fulfilled') {
        setArticles(digestRes.value.data.articles);
        setFresh(digestRes.value.data.fresh);
      }
      setHasProfile(profileRes.status === 'fulfilled');
    } catch (err) {
      console.error('Error fetching digest:', err);
    } finally {
      setLoading(false);
    }
  };

  const pollForResults = () => {
    setProgress({ evaluated: 0, total: 50 });
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
          setArticles(res.data.articles);
          setFresh(res.data.fresh);
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
    setArticles([]);
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
          <p className="digest-subtitle">Research matched to your classroom, ready to use.</p>
        </div>
        <button className="btn-refresh" onClick={handleRegenerate} disabled={regenerating}>
          {regenerating ? 'Generating…' : 'Refresh'}
        </button>
      </div>

      {regenerating ? (
        <div className="generating-state">
          <p className="generating-headline">Finding your articles…</p>
          <p className="generating-subtext">We're reading through recent research and matching it to your classroom. This page will update automatically when your digest is ready.</p>
          <div className="progress-bar-track">
            <div
              className="progress-bar-fill"
              style={{ width: `${Math.min(100, Math.round((progress.evaluated / progress.total) * 100))}%` }}
            />
          </div>
          <p className="progress-label">
            {progress.evaluated === 0
              ? 'Starting up…'
              : `${progress.evaluated} of ~${progress.total} articles evaluated`}
          </p>
        </div>
      ) : !hasProfile ? (
        <div className="welcome-state">
          <h2 className="welcome-headline">Your weekly research digest, matched to your classroom.</h2>
          <p className="welcome-body">Every week, Pace Edu finds peer-reviewed research relevant to what you're teaching and translates it into plain-language summaries and ready-to-use action steps. Takes 2 minutes to set up.</p>
          <Link to="/profile?onboarding=true" className="btn-start">Get started →</Link>
        </div>
      ) : articles.length === 0 ? (
        <div className="empty-state">
          Your digest is empty — click Refresh to generate your first reading list.
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
                    ? <a href={article.url} target="_blank" rel="noopener noreferrer">{article.title}</a>
                    : article.title}
                </h2>

                {meta && <p className="article-meta">{meta}</p>}

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
