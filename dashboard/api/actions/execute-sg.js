import { requireAuth } from '../_lib/auth';
import { forwardAction } from '../_lib/data';

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'method_not_allowed' });
  if (!requireAuth(req, res)) return;

  const out = await forwardAction('execute-sg');
  return res.status(out.ok ? 200 : 502).json(out);
}
