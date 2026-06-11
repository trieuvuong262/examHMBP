import { sleep, check } from 'k6';
import { loginSession, authGet, thinkTime } from './lib/auth.js';

const vus = Number(__ENV.STRESS_VUS || 10);
const duration = __ENV.STRESS_DURATION || '3m';
const ramp = __ENV.STRESS_RAMP || '30s';

export const options = {
  scenarios: {
    mixed_users: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: ramp, target: vus },
        { duration, target: vus },
        { duration: ramp, target: 0 },
      ],
      gracefulRampDown: '15s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.06'],
    http_req_duration: ['p(95)<6000'],
    checks: ['rate>0.88'],
  },
};

const MODULES = {
  reports: [
    '/reports/today/',
    '/reports/weekly/',
    '/reports/my/',
  ],
  requests: [
    '/yeu-cau/de-xuat/cua-toi/',
    '/yeu-cau/de-xuat/theo-doi/',
    '/yeu-cau/ho-tro/cua-toi/',
  ],
  kho: [
    '/kho-npl/tong-quan/',
    '/kho-npl/danh-muc/',
    '/kho-npl/ton-kho-npl/',
    '/kho-npl/kiem-ke/',
  ],
};

const MODULE_KEYS = Object.keys(MODULES);

export default function () {
  const session = loginSession();
  if (!session) {
    return;
  }

  authGet(session, '/', 'GET /');

  const moduleKey = MODULE_KEYS[Math.floor(Math.random() * MODULE_KEYS.length)];
  const paths = MODULES[moduleKey];

  for (const path of paths) {
    const res = authGet(session, path, `GET ${path}`);
    check(res, {
      [`${moduleKey} ${path} ok`]: (r) => r.status === 200 || r.status === 302,
    });
    sleep(0.3 + Math.random() * 0.5);
  }

  sleep(thinkTime());
}
