require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });
const express = require('express');
const cors = require('cors');
const path = require('path');
const authMiddleware = require('./middleware/auth');
const profileRoutes = require('./routes/profile');
const digestRoutes = require('./routes/digest');

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

// Public health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Apply auth middleware to all API routes below
app.use(authMiddleware);

app.use('/api/profile', profileRoutes);
app.use('/api/digest', digestRoutes);

// Serve built React frontend (production)
const distPath = path.join(__dirname, '..', 'frontend', 'dist');
app.use(express.static(distPath));
app.get(/.*/, (req, res) => {
  res.sendFile(path.join(distPath, 'index.html'));
});

app.listen(PORT, () => {
  console.log(`Pace AI Edu Backend listening on port ${PORT}`);
});
