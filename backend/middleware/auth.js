const ADMIN_EMAILS = () =>
  (process.env.ADMIN_EMAILS || '').split(',').map(e => e.trim().toLowerCase()).filter(Boolean);

const authMiddleware = (req, res, next) => {
  const email = req.headers['cf-access-authenticated-user-email'];

  if (!email) {
    if (process.env.NODE_ENV === 'development') {
      req.user = process.env.DEV_EMAIL || 'test-teacher@paceacademy.org';
      req.realUser = req.user;
      return next();
    }
    return res.status(401).json({ error: 'Unauthorized: Missing Cloudflare Access Header' });
  }

  req.realUser = email;

  const impersonate = req.headers['x-impersonate-email'];
  if (impersonate && ADMIN_EMAILS().includes(email.toLowerCase())) {
    req.user = impersonate.toLowerCase();
  } else {
    req.user = email;
  }

  next();
};

module.exports = authMiddleware;
