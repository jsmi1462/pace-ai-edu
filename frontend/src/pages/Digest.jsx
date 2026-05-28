import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { ExternalLink, CheckCircle, Lightbulb, Target } from 'lucide-react';

const Digest = () => {
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);

  useEffect(() => {
    fetchDigest();
  }, []);

  const fetchDigest = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`/api/digest/me`);
      setArticles(response.data);
    } catch (err) {
      console.error("Error fetching digest:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      await axios.post('/api/digest/regenerate');
      // In a real app, we might poll or wait for a websocket
      setTimeout(fetchDigest, 2000); 
    } catch (err) {
      console.error("Error regenerating digest:", err);
    } finally {
      setRegenerating(false);
    }
  };

  if (loading) return <div className="p-8">Loading your personalized digest...</div>;

  return (
    <div className="max-w-4xl mx-auto p-8">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-4xl font-extrabold text-slate-900">Your Research Digest</h1>
          <p className="text-slate-500 mt-2">Tailored classroom strategies based on the latest educational research.</p>
        </div>
        <button 
          onClick={handleRegenerate}
          disabled={regenerating}
          className={`px-4 py-2 rounded font-semibold transition ${
            regenerating 
              ? 'bg-slate-200 text-slate-400 cursor-not-allowed' 
              : 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-md'
          }`}
        >
          {regenerating ? 'Processing...' : 'Regenerate'}
        </button>
      </div>

      {articles.length === 0 ? (
        <div className="bg-slate-50 border-2 border-dashed border-slate-200 rounded-xl p-12 text-center">
          <p className="text-slate-500">No articles matched your profile yet. Make sure your profile is complete!</p>
        </div>
      ) : (
        <div className="space-y-8">
          {articles.map((article, index) => (
            <article key={index} className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden hover:shadow-md transition">
              <div className="p-6">
                <div className="flex justify-between items-start mb-4">
                  <span className="text-xs font-bold uppercase tracking-wider text-indigo-600 bg-indigo-50 px-2 py-1 rounded">
                    {article.source}
                  </span>
                  <a href={article.url} target="_blank" rel="noopener noreferrer" className="text-slate-400 hover:text-indigo-600">
                    <ExternalLink size={18} />
                  </a>
                </div>
                
                <h2 className="text-2xl font-bold text-slate-800 mb-1">{article.title}</h2>
                <p className="text-sm text-slate-500 mb-4">
                  {article.authors ? `${article.authors} • ` : ''}
                  {article.publication_date ? new Date(article.publication_date).toLocaleDateString() : 'Recent Research'}
                </p>
                
                <div className="flex items-start gap-3 mb-6">
                  <div className="mt-1 text-indigo-500"><Lightbulb size={20} /></div>
                  <p className="text-slate-600 leading-relaxed italic">"{article.summary}"</p>
                </div>

                <div className="space-y-4 mb-6">
                  <h3 className="text-sm font-bold uppercase tracking-widest text-slate-400 flex items-center gap-2">
                    <CheckCircle size={14} /> Actionable Steps for Tomorrow
                  </h3>
                  <ul className="grid gap-3">
                    {JSON.parse(article.action_steps || '[]').map((step, i) => (
                      <li key={i} className="flex gap-3 text-slate-700 bg-slate-50 p-3 rounded-lg border border-slate-100">
                        <span className="flex-shrink-0 w-6 h-6 rounded-full bg-white border border-slate-200 text-slate-500 text-xs flex items-center justify-center font-bold">
                          {i + 1}
                        </span>
                        {step}
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="bg-emerald-50 border border-emerald-100 rounded-lg p-4 flex gap-3">
                  <div className="text-emerald-600"><Target size={20} /></div>
                  <div>
                    <h4 className="text-xs font-bold uppercase tracking-widest text-emerald-700 mb-1">Institutional Alignment</h4>
                    <p className="text-sm text-emerald-800 leading-relaxed">{article.mission_alignment}</p>
                  </div>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
};

export default Digest;
