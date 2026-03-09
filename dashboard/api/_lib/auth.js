function unauthorized(res) {
  res.setHeader('WWW-Authenticate', 'Basic realm="OTTO Dashboard"');
  res.status(401).json({ error: 'unauthorized' });
}

export function requireAuth(req, res) {
  const expectedUser = process.env.DASHBOARD_AUTH_USER;
  const expectedPass = process.env.DASHBOARD_AUTH_PASS;

  if (!expectedUser || !expectedPass) return true;

  const header = req.headers.authorization || '';
  if (!header.startsWith('Basic ')) {
    unauthorized(res);
    return false;
  }

  const encoded = header.slice('Basic '.length);
  let decoded = '';
  try {
    decoded = Buffer.from(encoded, 'base64').toString('utf-8');
  } catch {
    unauthorized(res);
    return false;
  }

  const [user, pass] = decoded.split(':');
  if (user !== expectedUser || pass !== expectedPass) {
    unauthorized(res);
    return false;
  }

  return true;
}
