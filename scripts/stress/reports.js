import { sleep, check } from 'k6';
import { loginSession, authGet, thinkTime, defaultOptions } from './lib/auth.js';

export const options = defaultOptions();

const PAGES = [
  { path: '/reports/today/', name: 'GET /reports/today/' },
  { path: '/reports/weekly/', name: 'GET /reports/weekly/' },
  { path: '/reports/my/', name: 'GET /reports/my/' },
  { path: '/reports/my/?period=weekly', name: 'GET /reports/my/?period=weekly' },
  { path: '/reports/team/', name: 'GET /reports/team/' },
  { path: '/reports/team/weekly/', name: 'GET /reports/team/weekly/' },
];

export default function () {
  const session = loginSession();
  if (!session) {
    return;
  }

  authGet(session, '/', 'GET /');

  for (const page of PAGES) {
    const res = authGet(session, page.path, page.name);
    check(res, {
      [`${page.name} ok`]: (r) => r.status === 200 || r.status === 302,
    });
    sleep(0.3 + Math.random() * 0.7);
  }

  sleep(thinkTime());
}
