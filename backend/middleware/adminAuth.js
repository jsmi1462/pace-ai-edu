const adminAuth = (req, res, next) => {
  const adminEmails = (process.env.ADMIN_EMAILS || '')
    .split(',')
    .map(e => e.trim().toLowerCase())
    .filter(Boolean);

  if (!adminEmails.includes((req.user || '').toLowerCase())) {
    return res.status(403).json({ error: 'Admin access required' });
  }
  next();
};

module.exports = adminAuth;
