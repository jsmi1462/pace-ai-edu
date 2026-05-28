import React, { useState, useEffect } from 'react';
import axios from 'axios';

const Profile = () => {
  const [profile, setProfile] = useState({
    first_name: '',
    last_name: '',
    discipline: '',
    discipline_key: '',
    grade_band: '9-12',
    years_experience: 5,
    current_module: '',
    tailoring_query: ''
  });

  const disciplines = [
    { value: "ls_homeroom", label: "Lower School: Homeroom / Lead Teacher" },
    { value: "ls_math", label: "Lower School: Math" },
    { value: "ls_science", label: "Lower School: Science" },
    { value: "ls_steam", label: "Lower School: STEAM" },
    { value: "ls_world_language", label: "Lower School: World Language" },
    { value: "ls_arts", label: "Lower School: Arts & Music" },
    { value: "ls_pe", label: "Lower School: Physical Education" },
    { value: "ls_library", label: "Lower School: Library" },
    { value: "ls_learning_support", label: "Lower School: Learning Support" },
    { value: "ms_english", label: "Middle School: English" },
    { value: "ms_math", label: "Middle School: Math" },
    { value: "ms_science", label: "Middle School: Science" },
    { value: "ms_history", label: "Middle School: History & Social Studies" },
    { value: "ms_world_language", label: "Middle School: World Language" },
    { value: "ms_pe", label: "Middle School: Physical Education" },
    { value: "ms_steam", label: "Middle School: STEAM" },
    { value: "ms_arts", label: "Middle School: Arts & Music" },
    { value: "ms_debate", label: "Middle School: Debate" },
    { value: "us_english", label: "Upper School: English" },
    { value: "us_math", label: "Upper School: Math" },
    { value: "us_science", label: "Upper School: Science" },
    { value: "us_history", label: "Upper School: History & Social Studies" },
    { value: "us_world_language", label: "Upper School: World Language" },
    { value: "us_cs", label: "Upper School: Computer Science" },
    { value: "us_arts", label: "Upper School: Arts & Performing Arts" },
    { value: "us_social_science", label: "Upper School: Economics / Psychology / Social Sciences" },
    { value: "us_learning_support", label: "Upper School: Learning Support" },
    { value: "global_leadership", label: "Cross-Division: Global Leadership" },
    { value: "counseling", label: "Cross-Division: Counseling & SEL" }
  ];

  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const res = await axios.get('/api/profile');
        if (res.data) setProfile(res.data);
      } catch (err) {
        console.error('Error fetching profile:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchProfile();
  }, []);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setProfile(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage('Saving…');
    try {
      await axios.post('/api/profile', profile);
      setMessage('Saved.');
    } catch (err) {
      setMessage('Error saving.');
    }
  };

  if (loading) return <div className="page-content"><p className="loading">Loading…</p></div>;

  return (
    <div className="page-content">
      <h1 className="profile-title">Your Profile</h1>
      <p className="profile-subtitle">Tell us about your classroom so we know what to find for you.</p>

      <form onSubmit={handleSubmit}>
        <div className="form-grid">
          <div className="form-group">
            <label className="form-label">First Name</label>
            <input className="form-input" name="first_name" value={profile.first_name || ''} onChange={handleChange} required />
          </div>
          <div className="form-group">
            <label className="form-label">Last Name</label>
            <input className="form-input" name="last_name" value={profile.last_name || ''} onChange={handleChange} required />
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Teaching Discipline</label>
          <select className="form-input" name="discipline_key" value={profile.discipline_key || ''} onChange={handleChange} required>
            <option value="">Select a discipline...</option>
            {disciplines.map(d => (
              <option key={d.value} value={d.value}>{d.label}</option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Specific Subject/Role</label>
          <input className="form-input" name="discipline" value={profile.discipline || ''} onChange={handleChange} placeholder="e.g. 10th Grade History" required />
        </div>

        <div className="form-group">
          <label className="form-label">Grade Band</label>
          <select className="form-input" name="grade_band" value={profile.grade_band || ''} onChange={handleChange}>
            <option value="K-5">K–5</option>
            <option value="6-8">6–8</option>
            <option value="9-12">9–12</option>
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Years of Experience</label>
          <input className="form-input" type="number" name="years_experience" value={profile.years_experience || ''} onChange={handleChange} required />
        </div>

        <div className="form-group">
          <label className="form-label">Current Unit or Module</label>
          <input className="form-input" name="current_module" value={profile.current_module || ''} onChange={handleChange} placeholder="e.g. The French Revolution" />
        </div>

        <div className="form-group">
          <label className="form-label">What are your goals this year?</label>
          <textarea className="form-input" name="tailoring_query" value={profile.tailoring_query || ''} onChange={handleChange} placeholder="e.g. I want to improve student engagement during lectures…" />
        </div>

        <button type="submit" className="btn-save">Save Profile</button>
        {message && <p className="form-message">{message}</p>}
      </form>
    </div>
  );
};

export default Profile;
