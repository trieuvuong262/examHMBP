import { sleep, check } from 'k6';
import { loginSession, authGet, thinkTime, defaultOptions } from './lib/auth.js';

export const options = defaultOptions();

const PAGES = [
  { path: '/yeu-cau/de-xuat/cua-toi/', name: 'GET de-xuat my' },
  { path: '/yeu-cau/de-xuat/theo-doi/', name: 'GET de-xuat theo-doi' },
  { path: '/yeu-cau/de-xuat/cho-xu-ly/', name: 'GET de-xuat pending' },
  { path: '/yeu-cau/ho-tro/cua-toi/', name: 'GET ho-tro my' },
  { path: '/yeu-cau/ho-tro/theo-doi/', name: 'GET ho-tro theo-doi' },
  { path: '/yeu-cau/ho-tro/cho-xu-ly/', name: 'GET ho-tro pending' },
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
