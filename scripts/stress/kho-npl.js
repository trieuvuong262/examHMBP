import { sleep, check } from 'k6';
import { loginSession, authGet, thinkTime, defaultOptions } from './lib/auth.js';

export const options = defaultOptions({
  thresholds: {
    http_req_failed: ['rate<0.08'],
    http_req_duration: ['p(95)<8000'],
    checks: ['rate>0.85'],
  },
});

const PAGES = [
  { path: '/kho-npl/tong-quan/', name: 'GET kho-npl overview' },
  { path: '/kho-npl/danh-muc/', name: 'GET kho-npl materials' },
  { path: '/kho-npl/ton-kho-npl/', name: 'GET kho-npl stock' },
  { path: '/kho-npl/the-kho/', name: 'GET kho-npl stock cards' },
  { path: '/kho-npl/phieu-nhap/', name: 'GET kho-npl receipts' },
  { path: '/kho-npl/phieu-xuat/', name: 'GET kho-npl issues' },
  { path: '/kho-npl/kiem-ke/', name: 'GET kho-npl stocktakes' },
  { path: '/kho-npl/bao-cao/', name: 'GET kho-npl reports' },
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
    sleep(0.4 + Math.random() * 0.8);
  }

  sleep(thinkTime());
}
