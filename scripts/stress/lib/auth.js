import http from 'k6/http';
import { check } from 'k6';

export function getBaseUrl() {
  const base = (__ENV.STRESS_BASE_URL || 'https://portal.justplay.vn').replace(/\/$/, '');
  return base;
}

export function getCredentials() {
  return {
    username: __ENV.STRESS_USER || '',
    password: __ENV.STRESS_PASS || '',
  };
}

export function extractCsrf(html) {
  const body = typeof html === 'string' ? html : '';
  const hidden = body.match(/name="csrfmiddlewaretoken" value="([^"]+)"/);
  if (hidden) {
    return hidden[1];
  }
  const input = body.match(/csrfmiddlewaretoken['"]\s*value=['"]([^'"]+)['"]/);
  return input ? input[1] : null;
}

export function loginSession() {
  const baseUrl = getBaseUrl();
  const { username, password } = getCredentials();
  if (!username || !password) {
    throw new Error('Thieu STRESS_USER / STRESS_PASS (xem stress.env.example)');
  }

  const jar = http.cookieJar();
  const loginPage = http.get(`${baseUrl}/accounts/login/`, {
    jar,
    tags: { name: 'GET /accounts/login/' },
  });

  const pageOk = check(loginPage, {
    'login page 200': (r) => r.status === 200,
  });
  if (!pageOk) {
    return null;
  }

  const csrf = extractCsrf(loginPage.body);
  if (!csrf) {
    check(null, { 'csrf token found': () => false });
    return null;
  }

  const loginRes = http.post(
    `${baseUrl}/accounts/login/`,
    {
      username,
      password,
      csrfmiddlewaretoken: csrf,
      next: '/',
    },
    {
      jar,
      tags: { name: 'POST /accounts/login/' },
      headers: {
        Referer: `${baseUrl}/accounts/login/`,
        Origin: baseUrl,
      },
      redirects: 0,
    },
  );

  const loginOk = check(loginRes, {
    'login success': (r) => r.status === 302 || r.status === 303,
  });
  if (!loginOk) {
    return null;
  }

  return { jar, baseUrl };
}

export function authGet(session, path, name) {
  const url = path.startsWith('http') ? path : `${session.baseUrl}${path}`;
  return http.get(url, {
    jar: session.jar,
    tags: { name: name || `GET ${path}` },
  });
}

export function thinkTime() {
  const min = Number(__ENV.STRESS_SLEEP_MIN || 2);
  const max = Number(__ENV.STRESS_SLEEP_MAX || 5);
  const span = Math.max(0, max - min);
  return min + Math.random() * span;
}

export function defaultOptions(overrides = {}) {
  const vus = Number(__ENV.STRESS_VUS || 10);
  const duration = __ENV.STRESS_DURATION || '3m';
  const ramp = __ENV.STRESS_RAMP || '30s';

  return {
    stages: [
      { duration: ramp, target: vus },
      { duration, target: vus },
      { duration: ramp, target: 0 },
    ],
    thresholds: {
      http_req_failed: ['rate<0.05'],
      http_req_duration: ['p(95)<5000'],
      checks: ['rate>0.90'],
    },
    ...overrides,
  };
}
