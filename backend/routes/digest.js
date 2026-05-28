const express = require('express');
const router = express.Router();
const { Pool } = require('pg');

const pool = new Pool({
  connectionString: process.env.DATABASE_URL
});

// GET /digest/me - Fetch matched articles for the logged-in teacher
router.get('/me', async (req, res) => {
  const email = req.user;
  
  try {
    const query = `
      SELECT 
        a.title, 
        a.source, 
        a.url, 
        a.authors,
        a.publication_date,
        tam.summary, 
        tam.action_steps, 
        tam.mission_alignment, 
        tam.similarity_score,
        tam.date_evaluated
      FROM teacher_article_matches tam
      JOIN articles a ON tam.article_id = a.id
      WHERE tam.teacher_email = $1 
        AND tam.decision = 'Yes'
      ORDER BY tam.date_evaluated DESC, tam.similarity_score DESC
      LIMIT 10;
    `;
    const result = await pool.query(query, [email]);
    res.json(result.rows);
  } catch (err) {
    console.error(err);
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
