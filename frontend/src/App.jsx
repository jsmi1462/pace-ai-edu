import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import Profile from './pages/Profile';
import Digest from './pages/Digest';

function NavLink({ to, children }) {
  const { pathname } = useLocation();
  return (
    <Link to={to} className={pathname === to ? 'active' : ''}>
      {children}
    </Link>
  );
}

function App() {
  return (
    <Router>
      <div>
        <header className="site-header">
          <div className="site-header-inner">
            <Link to="/" className="wordmark">Pace Edu</Link>
            <nav className="site-nav">
              <NavLink to="/">Digest</NavLink>
              <NavLink to="/profile">Profile</NavLink>
            </nav>
          </div>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<Digest />} />
            <Route path="/profile" element={<Profile />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
