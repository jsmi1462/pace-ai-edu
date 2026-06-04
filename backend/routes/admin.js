const express = require('express');
const router = express.Router();
const { spawn } = require('child_process');
const path = require('path');

const pool = require('../db');

const pythonBin = () => process.env.PYTHON_BIN || 'python3';
const projectRoot = path.join(__dirname, '..', '..');

let runAllActive = false;
const teacherRunning = new Set();
const activeProcs = new Map();   // email | '__all__' -> proc
const logBuffers = new Map();    // email | '__all__' -> [{ts, line, stream}]
const runHistory = [];           // last MAX_HISTORY entries
const MAX_LOG_LINES = 500;
const MAX_HISTORY = 50;

function appendLog(key, stream, data) {
  if (!logBuffers.has(key)) logBuffers.set(key, []);
  const buf = logBuffers.get(key);
  const lines = data.toString().split('\n');
  for (const line of lines) {
    if (!line.trim()) continue;
    buf.push({ ts: new Date().toISOString(), line, stream });
    if (buf.length > MAX_LOG_LINES) buf.shift();
  }
}

function addHistory(entry) {
  runHistory.push(entry);
  if (runHistory.length > MAX_HISTORY) runHistory.shift();
}

router.get('/check', (req, res) => res.json({ ok: true }));

router.get('/pipeline-status', (req, res) => {
  const logs = {};
  for (const [key, buf] of logBuffers.entries()) {
    logs[key] = buf.slice(-200);
  }
  res.json({
    runAllActive,
    running: [...teacherRunning],
    logs,
    history: runHistory.slice().reverse(),
  });
});

router.get('/users', async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT
        fp.email,
        fp.first_name,
        fp.last_name,
        fp.discipline,
        fp.grade_band,
        fp.years_experience,
        fp.is_active,
        COUNT(CASE WHEN tam.decision = 'Yes' AND tam.status = 'pending' THEN 1 END)::int  AS pending,
        COUNT(CASE WHEN tam.status = 'sent' THEN 1 END)::int                              AS sent,
        COUNT(CASE WHEN tam.date_evaluated = CURRENT_DATE AND tam.decision = 'Yes' THEN 1 END)::int AS today_matches,
        COUNT(CASE WHEN tam.date_evaluated = CURRENT_DATE THEN 1 END)::int                AS today_evaluated,
        COUNT(CASE WHEN tam.decision = 'Yes' THEN 1 END)::int                             AS total_matched,
        COUNT(CASE WHEN tam.decision = 'No'  THEN 1 END)::int                             AS total_rejected,
        COUNT(CASE WHEN tam.decision = 'Error' THEN 1 END)::int                           AS total_errors,
        COUNT(tam.id)::int                                                                 AS total_evaluated,
        ROUND(
          COUNT(CASE WHEN tam.decision = 'Yes' THEN 1 END)::numeric /
          NULLIF(COUNT(CASE WHEN tam.decision IN ('Yes','No') THEN 1 END), 0) * 100, 1
        )                                                                                  AS match_rate,
        MAX(tam.date_evaluated)                                                            AS last_evaluated
      FROM faculty_profiles fp
      LEFT JOIN teacher_article_matches tam ON tam.teacher_email = fp.email
      GROUP BY fp.email, fp.first_name, fp.last_name, fp.discipline, fp.grade_band,
               fp.years_experience, fp.is_active
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
    const [summary, sources, trend] = await Promise.all([
      pool.query(`
        SELECT
          (SELECT COUNT(*) FROM articles)::int                                            AS total,
          (SELECT COUNT(*) FROM articles WHERE created_at::date = CURRENT_DATE)::int      AS ingested_today,
          (SELECT COUNT(*) FROM faculty_profiles)::int                                    AS total_teachers,
          (SELECT COUNT(*) FROM faculty_profiles WHERE is_active = true)::int             AS active_teachers,
          COUNT(CASE WHEN tam.decision = 'Yes'   THEN 1 END)::int                        AS matched,
          COUNT(CASE WHEN tam.decision = 'No'    THEN 1 END)::int                        AS rejected,
          COUNT(CASE WHEN tam.decision = 'Error' THEN 1 END)::int                        AS errors,
          COUNT(CASE WHEN tam.date_evaluated = CURRENT_DATE THEN 1 END)::int             AS today,
          COUNT(CASE WHEN tam.date_evaluated = CURRENT_DATE AND tam.decision = 'Yes' THEN 1 END)::int AS today_matched,
          ROUND(
            COUNT(CASE WHEN tam.decision = 'Yes' THEN 1 END)::numeric /
            NULLIF(COUNT(CASE WHEN tam.decision IN ('Yes','No') THEN 1 END), 0) * 100, 1
          )                                                                               AS match_rate
        FROM teacher_article_matches tam
      `),
      pool.query(`
        SELECT source, COUNT(*)::int AS count
        FROM articles
        GROUP BY source
        ORDER BY count DESC
      `),
      pool.query(`
        SELECT
          gs.day::date AS day,
          COALESCE(cnt.count, 0)::int AS count
        FROM generate_series(
          CURRENT_DATE - INTERVAL '6 days',
          CURRENT_DATE,
          INTERVAL '1 day'
        ) AS gs(day)
        LEFT JOIN (
          SELECT created_at::date AS d, COUNT(*)::int AS count
          FROM articles
          WHERE created_at >= CURRENT_DATE - INTERVAL '6 days'
          GROUP BY created_at::date
        ) cnt ON cnt.d = gs.day::date
        ORDER BY gs.day
      `),
    ]);
    res.json({
      ...summary.rows[0],
      sources: sources.rows,
      trend: trend.rows,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Database error' });
  }
});

router.post('/regenerate/:email', (req, res) => {
  const { email } = req.params;
  if (runAllActive || teacherRunning.has(email)) {
    return res.status(409).json({ error: 'Pipeline already running for this teacher' });
  }
  teacherRunning.add(email);
  logBuffers.set(email, []);
  const startedAt = new Date().toISOString();
  const proc = spawn(pythonBin(), ['-m', 'pipeline.workflow', '--teacher', email], { cwd: projectRoot });
  activeProcs.set(email, proc);
  proc.stdout.on('data', d => appendLog(email, 'stdout', d));
  proc.stderr.on('data', d => appendLog(email, 'stderr', d));
  proc.on('close', (code) => {
    teacherRunning.delete(email);
    activeProcs.delete(email);
    addHistory({ type: 'teacher', target: email, startedAt, endedAt: new Date().toISOString(), exitCode: code });
    if (code !== 0) console.error(`Pipeline failed for ${email} with exit code ${code}`);
  });
  res.json({ message: `Pipeline started for ${email}` });
});

router.post('/run-all', (req, res) => {
  if (runAllActive) return res.status(409).json({ error: 'Pipeline already running' });
  runAllActive = true;
  logBuffers.set('__all__', []);
  const startedAt = new Date().toISOString();
  const proc = spawn(pythonBin(), ['-m', 'pipeline.workflow'], { cwd: projectRoot });
  activeProcs.set('__all__', proc);
  proc.stdout.on('data', d => appendLog('__all__', 'stdout', d));
  proc.stderr.on('data', d => appendLog('__all__', 'stderr', d));
  proc.on('close', (code) => {
    runAllActive = false;
    activeProcs.delete('__all__');
    addHistory({ type: 'all', target: null, startedAt, endedAt: new Date().toISOString(), exitCode: code });
    if (code !== 0) console.error(`Full pipeline run failed with exit code ${code}`);
  });
  res.json({ message: 'Full pipeline started for all teachers' });
});

router.post('/cancel/:key', (req, res) => {
  const rawKey = req.params.key;
  const procKey = rawKey === 'all' ? '__all__' : rawKey;
  const proc = activeProcs.get(procKey);
  if (!proc) return res.status(404).json({ error: 'No active process found' });
  try {
    proc.kill('SIGTERM');
    appendLog(procKey, 'stderr', `[admin] Process cancelled by user at ${new Date().toISOString()}`);
    res.json({ message: 'Process terminated' });
  } catch (e) {
    res.status(500).json({ error: 'Failed to kill process' });
  }
});

module.exports = router;
