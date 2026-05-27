import React, { useState, useEffect } from 'react';
import axios from 'axios';

const Profile = () => {
  const [profile, setProfile] = useState({
    first_name: '',
    last_name: '',
    discipline: '',
    grade_band: '9-12',
    years_experience: 5,
    current_module: '',
    tailoring_query: ''
  });
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const response = await axios.get('/api/profile');
        if (response.data) {
          setProfile(response.data);
        }
      } catch (err) {
        console.error("Error fetching profile:", err);
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
    setMessage('Saving...');
    try {
      await axios.post('/api/profile', profile);
      setMessage('Profile saved successfully!');
    } catch (err) {
      console.error("Error saving profile:", err);
      setMessage('Error saving profile.');
    }
  };

  if (loading) return <div className="p-8">Loading profile...</div>;

  return (
    <div className="max-w-2xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-6">Teacher Profile Setup</h1>
      <p className="mb-6 text-gray-600">Tell us about your classroom so we can tailor your research digest.</p>
      
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">First Name</label>
            <input 
              name="first_name" 
              value={profile.first_name || ''} 
              onChange={handleChange}
              className="w-full p-2 border rounded"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Last Name</label>
            <input 
              name="last_name" 
              value={profile.last_name || ''} 
              onChange={handleChange}
              className="w-full p-2 border rounded"
              required
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Discipline (e.g. AP Chemistry, 7th Grade English)</label>
          <input 
            name="discipline" 
            value={profile.discipline || ''} 
            onChange={handleChange}
            placeholder="e.g. 10th Grade History"
            className="w-full p-2 border rounded"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Grade Band</label>
          <select 
            name="grade_band" 
            value={profile.grade_band || ''} 
            onChange={handleChange}
            className="w-full p-2 border rounded"
          >
            <option value="K-5">K-5</option>
            <option value="6-8">6-8</option>
            <option value="9-12">9-12</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Years of Experience</label>
          <input 
            type="number"
            name="years_experience" 
            value={profile.years_experience || ''} 
            onChange={handleChange}
            className="w-full p-2 border rounded"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Current Module / Unit</label>
          <input 
            name="current_module" 
            value={profile.current_module || ''} 
            onChange={handleChange}
            placeholder="e.g. The French Revolution"
            className="w-full p-2 border rounded"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Tailoring Query (What are your goals?)</label>
          <textarea 
            name="tailoring_query" 
            value={profile.tailoring_query || ''} 
            onChange={handleChange}
            placeholder="e.g. I want to improve student engagement during lectures..."
            className="w-full p-2 border rounded h-32"
          />
        </div>

        <button 
          type="submit" 
          className="bg-blue-600 text-white px-6 py-2 rounded font-bold hover:bg-blue-700 transition"
        >
          Save Profile
        </button>
        
        {message && <p className="mt-4 font-medium">{message}</p>}
      </form>
    </div>
  );
};

export default Profile;
