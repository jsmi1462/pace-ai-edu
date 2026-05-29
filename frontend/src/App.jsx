import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
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

function App() {
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    axios.get('/api/admin/check').then(() => setIsAdmin(true)).catch(() => {});
  }, []);

  return (
    <Router>
      <div>
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
    </Router>
  );
}

export default App;
