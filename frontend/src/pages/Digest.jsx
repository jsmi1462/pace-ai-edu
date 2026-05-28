import React, { useState, useEffect, useRef } from 'react';
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
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const pollRef = useRef(null);
  const pollStartRef = useRef(null);

  useEffect(() => { fetchDigest(); return () => stopPolling(); }, []);

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  const fetchDigest = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/digest/me');
      setArticles(res.data);
    } catch (err) {
      console.error('Error fetching digest:', err);
    } finally {
      setLoading(false);
    }
  };

  const pollForResults = () => {
    pollStartRef.current = Date.now();
    pollRef.current = setInterval(async () => {
      if (Date.now() - pollStartRef.current > POLL_TIMEOUT) {
        stopPolling();
        setRegenerating(false);
        return;
      }
      try {
        const res = await axios.get('/api/digest/me');
        if (res.data.length > 0) {
          setArticles(res.data);
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
          <p className="generating-subtext">The AI is reading through research right now. This takes a few minutes — sit tight.</p>
        </div>
      ) : articles.length === 0 ? (
        <div className="empty-state">
          No articles yet — fill out your profile so we know what to look for.
        </div>
      ) : (
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
      )}
    </div>
  );
};

export default Digest;
