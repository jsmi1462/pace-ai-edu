import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import Profile from './pages/Profile';
import Digest from './pages/Digest';
import { BookOpen, User } from 'lucide-react';

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-slate-50 font-sans text-slate-900">
        <nav className="bg-white border-b border-slate-200 sticky top-0 z-10">
          <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="bg-indigo-600 p-1.5 rounded-lg text-white">
                <BookOpen size={20} />
              </div>
              <span className="font-black text-xl tracking-tight">Pace AI <span className="text-indigo-600">Edu</span></span>
            </div>
            <div className="flex gap-6">
              <Link to="/" className="text-sm font-semibold text-slate-600 hover:text-indigo-600 transition flex items-center gap-2">
                <BookOpen size={16} /> Digest
              </Link>
              <Link to="/profile" className="text-sm font-semibold text-slate-600 hover:text-indigo-600 transition flex items-center gap-2">
                <User size={16} /> Profile
              </Link>
            </div>
          </div>
        </nav>

        <main className="max-w-6xl mx-auto py-8">
          <Routes>
            <Route path="/" element={<Digest />} />
            <Route path="/profile" element={<Profile />} />
          </Routes>
        </main>
        
        <footer className="border-t border-slate-200 py-8 bg-white">
          <div className="max-w-6xl mx-auto px-4 text-center text-slate-400 text-sm">
            &copy; {new Date().getFullYear()} Pace Academy Educational Digest. 
            <span className="mx-2">|</span>
            Connecting Research to Practice.
          </div>
        </footer>
      </div>
    </Router>
  );
}

export default App;
