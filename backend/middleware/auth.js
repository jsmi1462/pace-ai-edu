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

  req.user = email;
  next();
};

module.exports = authMiddleware;
