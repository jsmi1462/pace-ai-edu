const express = require('express');
const router = express.Router();
const { Pool } = require('pg');
const { spawn } = require('child_process');
const path = require('path');

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

router.get('/check', (req, res) => res.json({ ok: true }));

router.get('/users', async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT
        fp.email,
        fp.first_name,
        fp.last_name,
        fp.discipline,
        fp.grade_band,
        COUNT(CASE WHEN tam.decision = 'Yes' AND tam.status = 'pending' THEN 1 END)::int AS pending,
        COUNT(CASE WHEN tam.status = 'sent' THEN 1 END)::int AS sent,
        MAX(tam.date_evaluated) AS last_evaluated
      FROM faculty_profiles fp
      LEFT JOIN teacher_article_matches tam ON tam.teacher_email = fp.email
      GROUP BY fp.email, fp.first_name, fp.last_name, fp.discipline, fp.grade_band
      ORDER BY fp.last_name, fp.first_name
    `);
    res.json(result.rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Database error' });
  }
});

router.get('/articles', async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT
        (SELECT COUNT(*) FROM articles)::int AS total,
        COUNT(CASE WHEN tam.decision = 'Yes' THEN 1 END)::int AS matched,
        COUNT(CASE WHEN tam.decision = 'No' THEN 1 END)::int AS rejected,
        COUNT(CASE WHEN tam.date_evaluated = CURRENT_DATE THEN 1 END)::int AS today
      FROM teacher_article_matches tam
    `);
    res.json(result.rows[0]);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Database error' });
  }
});

router.post('/regenerate/:email', (req, res) => {
  const { email } = req.params;
  const pythonBin = process.env.PYTHON_BIN || 'python3';
  const cwd = path.join(__dirname, '..', '..');

  const proc = spawn(pythonBin, ['-m', 'pipeline.workflow', '--teacher', email], { cwd });
  proc.on('close', (code) => {
    if (code !== 0) console.error(`Pipeline failed for ${email} with exit code ${code}`);
  });

  res.json({ message: `Pipeline started for ${email}` });
});

module.exports = router;
