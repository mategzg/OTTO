import { requireAuth } from './_lib/auth';
import { getDashboardPayload } from './_lib/data';

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.status(405).json({ error: 'method_not_allowed' });
    return;
  }

  if (!requireAuth(req, res)) return;

  const payload = await getDashboardPayload();
  res.setHeader('Cache-Control', 'no-store');
  res.status(200).json(payload);
}
