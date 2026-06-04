const express = require('express');
const router = express.Router();
const pool = require('../db');

// GET /digest/me - Fetch matched articles for the logged-in teacher
// Optional ?date=YYYY-MM-DD to load a specific past run.
router.get('/me', async (req, res) => {
  const email = req.user;
  const requestedDate = req.query.date || null;

  try {
    // All dates that have Yes matches for this teacher, newest first
    const datesResult = await pool.query(
      `SELECT DISTINCT date_evaluated::text
       FROM teacher_article_matches
       WHERE teacher_email = $1 AND decision = 'Yes' AND date_evaluated IS NOT NULL
       ORDER BY date_evaluated DESC`,
      [email]
    );
    const dates = datesResult.rows.map(r => r.date_evaluated);
    const latestDate = dates[0] || null;
    const targetDate = requestedDate || latestDate;

    if (!targetDate) {
      return res.json({ articles: [], dates: [], currentDate: null, fresh: false });
    }

    const result = await pool.query(
      `SELECT
         a.id AS article_id, a.title, a.source, a.url, a.authors, a.publication_date,
         tam.summary, tam.action_steps, tam.mission_alignment,
         tam.similarity_score, tam.date_evaluated, tam.status, tam.user_rating
       FROM teacher_article_matches tam
       JOIN articles a ON tam.article_id = a.id
       WHERE tam.teacher_email = $1
         AND tam.decision = 'Yes'
         AND tam.date_evaluated = $2
       ORDER BY tam.similarity_score DESC
       LIMIT 10`,
      [email, targetDate]
    );

    const isLatest = targetDate === latestDate;
    const fresh = isLatest && result.rows.some(r => r.status === 'pending');

    if (fresh) {
      await pool.query(
        `UPDATE teacher_article_matches SET status = 'sent'
         WHERE teacher_email = $1 AND decision = 'Yes' AND date_evaluated = $2 AND status = 'pending'`,
        [email, targetDate]
      );
    }

    res.json({ articles: result.rows, dates, currentDate: targetDate, fresh });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Database error' });
  }
});

// GET /digest/progress - How many articles evaluated today for this teacher
router.get('/progress', async (req, res) => {
  const email = req.user;
  try {
    const result = await pool.query(
      `SELECT COUNT(*) AS evaluated
       FROM teacher_article_matches
       WHERE teacher_email = $1
         AND date_evaluated = CURRENT_DATE`,
      [email]
    );
    const evaluated = parseInt(result.rows[0].evaluated, 10);
    res.json({ evaluated, total: 50 });
  } catch (err) {
    res.status(500).json({ error: 'Database error' });
  }
});

// GET /digest/:email - Fetch matched articles for a teacher (legacy support)
router.get('/:email', async (req, res) => {
  const { email } = req.params;
  if (req.user !== email) {
    return res.status(403).json({ error: 'Forbidden' });
  }
  try {
    const result = await pool.query('SELECT * FROM articles LIMIT 1'); // Placeholder for legacy
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: 'DB error' });
  }
});

// POST /digest/rate — save a user rating for an article
router.post('/rate', async (req, res) => {
  const email = req.user;
  const { article_id, rating } = req.body;
  const valid = ['awesome', 'good', 'bad', 'irrelevant', null];
  if (!article_id || !valid.includes(rating)) {
    return res.status(400).json({ error: 'Invalid article_id or rating' });
  }
  try {
    await pool.query(
      `UPDATE teacher_article_matches SET user_rating = $1
       WHERE teacher_email = $2 AND article_id = $3`,
      [rating, email, article_id]
    );
    res.json({ ok: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Database error' });
  }
});

const { spawn } = require('child_process');

// POST /digest/regenerate - Trigger pipeline (Task 4.3)
router.post('/regenerate', async (req, res) => {
  const email = req.user; // Use the authenticated user's email
  
  console.log(`Triggering pipeline for ${email}...`);
  
  // Use venv python so all pipeline deps are available
  const pythonBin = process.env.PYTHON_BIN || 'python3';
  const cwd = require('path').join(__dirname, '..', '..');
  const pythonProcess = spawn(pythonBin, [
    '-m', 'pipeline.workflow',
    '--teacher', email
  ], { cwd });

  let output = '';
  let error = '';

  pythonProcess.stdout.on('data', (data) => {
    output += data.toString();
  });

  pythonProcess.stderr.on('data', (data) => {
    error += data.toString();
  });

  pythonProcess.on('close', (code) => {
    console.log(`Pipeline finished with code ${code}`);
    if (code === 0) {
      console.log('Pipeline output:', output);
    } else {
      console.error('Pipeline error:', error);
    }
  });

  // Respond immediately so the UI doesn't hang
  res.json({ 
    message: 'Pipeline trigger received. Processing started in background.',
    target: email
  });
});

module.exports = router;
