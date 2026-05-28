const authMiddleware = (req, res, next) => {
  const email = req.headers['cf-access-authenticated-user-email'];
  
  if (!email) {
    // In development/local mode, we might want a fallback or to skip this
    // For now, let's follow the requirement but add a check for local dev
    if (process.env.NODE_ENV === 'development') {
      req.user = process.env.DEV_EMAIL || 'test-teacher@paceacademy.org';
      return next();
    }
    return res.status(401).json({ error: 'Unauthorized: Missing Cloudflare Access Header' });
  }

  // Restrict to @paceacademy.org
  if (!email.endsWith('@paceacademy.org')) {
    return res.status(403).json({ error: 'Forbidden: Access restricted to @paceacademy.org domain' });
  }

  req.user = email;
  next();
};

module.exports = authMiddleware;
