const express = require('express');
const router = express.Router();
const { Pool } = require('pg');

const pool = new Pool({
  connectionString: process.env.DATABASE_URL
});

// GET /digest/:email - Fetch matched articles for a teacher
router.get('/:email', async (req, res) => {
  const { email } = req.params;

  // Security check: only allow users to see their own digest
  // unless they are some kind of admin (not specified yet)
  if (req.user !== email) {
    return res.status(403).json({ error: 'Forbidden: You can only access your own digest' });
  }

  try {
    const query = `
      SELECT 
        a.title, 
        a.source, 
        a.url, 
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

// POST /digest/regenerate - Trigger pipeline (Task 4.3)
router.post('/regenerate', async (req, res) => {
  // This would typically trigger the Python pipeline.
  // For now, it's a placeholder scaffold.
  // We might use child_process or hit a separate internal endpoint.
  res.json({ message: 'Pipeline trigger received. Processing digest...' });
});

module.exports = router;
