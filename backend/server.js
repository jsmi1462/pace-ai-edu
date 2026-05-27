require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });
const express = require('express');
const cors = require('cors');
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

// Apply auth middleware to all routes below
app.use(authMiddleware);

app.use('/profile', profileRoutes);
app.use('/digest', digestRoutes);

app.listen(PORT, () => {
  console.log(`Pace AI Edu Backend listening on port ${PORT}`);
});
