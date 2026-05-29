import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import Profile from './pages/Profile';
import Digest from './pages/Digest';
import Admin from './pages/Admin';

function NavLink({ to, children }) {
  const { pathname } = useLocation();
  return (
    <Link to={to} className={pathname === to ? 'active' : ''}>
      {children}
    </Link>
  );
}

function AppInner() {
  const [isAdmin, setIsAdmin] = useState(false);
  const [impersonating, setImpersonating] = useState(() => localStorage.getItem('impersonating'));
  const navigate = useNavigate();

  useEffect(() => {
    axios.get('/api/admin/check').then(() => setIsAdmin(true)).catch(() => {});
  }, []);

  useEffect(() => {
    const id = axios.interceptors.request.use(config => {
      const target = localStorage.getItem('impersonating');
      if (target) config.headers['X-Impersonate-Email'] = target;
      return config;
    });
    return () => axios.interceptors.request.eject(id);
  }, []);

  useEffect(() => {
    const handler = () => setImpersonating(localStorage.getItem('impersonating'));
    window.addEventListener('impersonation-change', handler);
    return () => window.removeEventListener('impersonation-change', handler);
  }, []);

  const stopImpersonating = () => {
    localStorage.removeItem('impersonating');
    setImpersonating(null);
    navigate('/admin');
  };

  return (
    <div>
      {impersonating && (
        <div className="impersonation-banner">
          Viewing as <strong>{impersonating}</strong>
          <button className="btn-exit-impersonation" onClick={stopImpersonating}>Exit ×</button>
        </div>
      )}
      <header className="site-header">
        <div className="site-header-inner">
          <Link to="/" className="wordmark">Pace Edu</Link>
          <nav className="site-nav">
            <NavLink to="/">Digest</NavLink>
            <NavLink to="/profile">Profile</NavLink>
            {isAdmin && <NavLink to="/admin">Admin</NavLink>}
          </nav>
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Digest />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </main>
    </div>
  );
}

function App() {
  return (
    <Router>
      <AppInner />
    </Router>
  );
}

export default App;
