const express = require('express');
const router = express.Router();
const { Pool } = require('pg');

const pool = new Pool({
  connectionString: process.env.DATABASE_URL
});

// GET /profile - Get profile for the authenticated user
router.get('/', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM faculty_profiles WHERE email = $1', [req.user]);
    if (result.rows.length === 0) {
      return res.status(404).json({ message: 'Profile not found' });
    }
    res.json(result.rows[0]);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Database error' });
  }
});

// POST /profile - Create or update profile
router.post('/', async (req, res) => {
  const { first_name, last_name, discipline, grade_band, years_experience, current_module, tailoring_query, discipline_key } = req.body;
  const email = req.user;

  try {
    const query = `
      INSERT INTO faculty_profiles (email, first_name, last_name, discipline, grade_band, years_experience, current_module, tailoring_query, discipline_key)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
      ON CONFLICT (email) DO UPDATE SET
        first_name = EXCLUDED.first_name,
        last_name = EXCLUDED.last_name,
        discipline = EXCLUDED.discipline,
        grade_band = EXCLUDED.grade_band,
        years_experience = EXCLUDED.years_experience,
        current_module = EXCLUDED.current_module,
        tailoring_query = EXCLUDED.tailoring_query,
        discipline_key = EXCLUDED.discipline_key,
        updated_at = CURRENT_TIMESTAMP
      RETURNING *;
    `;
    const result = await pool.query(query, [email, first_name, last_name, discipline, grade_band, years_experience, current_module, tailoring_query, discipline_key]);
    res.json(result.rows[0]);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Database error' });
  }
});

module.exports = router;
