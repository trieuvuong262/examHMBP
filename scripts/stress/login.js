import { sleep, check } from 'k6';
import { loginSession, authGet, thinkTime, defaultOptions } from './lib/auth.js';

export const options = defaultOptions({
  thresholds: {
    http_req_failed: ['rate<0.02'],
    http_req_duration: ['p(95)<3000'],
    checks: ['rate>0.95'],
  },
});

export default function () {
  const session = loginSession();
  if (!session) {
    return;
  }

  const home = authGet(session, '/', 'GET /');
  check(home, {
    'home ok': (r) => r.status === 200,
  });

  sleep(thinkTime());
}
