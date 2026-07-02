(function () {
  'use strict';

  const botPattern = /(bot|crawler|spider|slurp|scrapy|curl|wget|python-requests|headless|phantom|gptbot|chatgpt|ccbot|claudebot|anthropic|perplexity|bytespider|google-extended|facebookexternalhit|facebookbot|amazonbot|applebot-extended)/i;
  const storageKey = 'krPopAtlasHumanConfirmed';

  function safeStorageGet(key) {
    try { return localStorage.getItem(key) || ''; } catch (e) { return ''; }
  }

  function safeSessionGet(key) {
    try { return sessionStorage.getItem(key) || ''; } catch (e) { return ''; }
  }

  function safeSessionSet(key, value) {
    try { sessionStorage.setItem(key, value); } catch (e) {}
  }

  function allowInteractiveTarget(el) {
    return el && el.closest && el.closest('input,textarea,select,button,[contenteditable="true"]');
  }

  async function loadRuntimeConfig() {
    try {
      const resp = await fetch('runtime-env.json', { cache: 'no-store' });
      if (!resp.ok) return;
      const cfg = await resp.json();
      for (const key of ['CAPTCHA_PROVIDER', 'CAPTCHA_SITE_KEY', 'CAPTCHA_VERIFY_ENDPOINT', 'TURNSTILE_SITE_KEY', 'RECAPTCHA_SITE_KEY']) {
        if (cfg[key]) window[key] = cfg[key];
      }
    } catch (e) {}
  }

  function readRuntimeSetting(name) {
    const aliases = {
      CAPTCHA_SITE_KEY: ['CAPTCHA_SITE_KEY', 'TURNSTILE_SITE_KEY', 'RECAPTCHA_SITE_KEY'],
      CAPTCHA_PROVIDER: ['CAPTCHA_PROVIDER'],
      CAPTCHA_VERIFY_ENDPOINT: ['CAPTCHA_VERIFY_ENDPOINT']
    }[name] || [name];

    for (const key of aliases) {
      if (window[key]) return String(window[key]).trim();
      const stored = safeStorageGet(key);
      if (stored) return stored;
    }
    return '';
  }

  async function loadExternalScript(src, globalName) {
    if (globalName && window[globalName]) return window[globalName];
    await new Promise((resolve, reject) => {
      const existing = [...document.scripts].find(s => s.src === src);
      if (existing) {
        existing.addEventListener('load', resolve, { once: true });
        existing.addEventListener('error', reject, { once: true });
        return;
      }
      const script = document.createElement('script');
      script.src = src;
      script.async = true;
      script.defer = true;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
    return globalName ? window[globalName] : null;
  }

  async function init() {
    await loadRuntimeConfig();

    const gate = document.getElementById('human-gate');
    const btn = document.getElementById('human-gate-btn');
    const captchaWrap = document.getElementById('human-captcha-wrap');
    const captchaWidget = document.getElementById('human-captcha-widget');
    const captchaStatus = document.getElementById('human-captcha-status');
    const isLikelyBot = botPattern.test(navigator.userAgent || '') || navigator.webdriver === true;

    document.body.classList.add('copy-locked');

    const setStatus = text => {
      if (captchaStatus) captchaStatus.textContent = text || '';
    };

    const unlock = () => {
      safeSessionSet(storageKey, '1');
      document.body.classList.add('human-ok');
      document.body.classList.remove('guard-pending');
      gate?.setAttribute('aria-hidden', 'true');
    };

    const providerRaw = readRuntimeSetting('CAPTCHA_PROVIDER').toLowerCase();
    let provider = providerRaw === 'cloudflare' ? 'turnstile' : providerRaw === 'google' ? 'recaptcha' : providerRaw;
    const turnstileKey = window.TURNSTILE_SITE_KEY || safeStorageGet('TURNSTILE_SITE_KEY');
    const recaptchaKey = window.RECAPTCHA_SITE_KEY || safeStorageGet('RECAPTCHA_SITE_KEY');
    if (!provider) provider = turnstileKey ? 'turnstile' : (recaptchaKey ? 'recaptcha' : '');
    const siteKey = provider === 'turnstile'
      ? (turnstileKey || readRuntimeSetting('CAPTCHA_SITE_KEY'))
      : provider === 'recaptcha'
        ? (recaptchaKey || readRuntimeSetting('CAPTCHA_SITE_KEY'))
        : readRuntimeSetting('CAPTCHA_SITE_KEY');
    const verifyEndpoint = readRuntimeSetting('CAPTCHA_VERIFY_ENDPOINT');
    const captchaRequired = !!provider && !!siteKey;
    let captchaVerified = !captchaRequired;

    const enableAfterCaptcha = () => {
      captchaVerified = true;
      if (btn) {
        btn.disabled = false;
        btn.textContent = '확인하고 보기';
      }
      setStatus('사람 확인이 완료되었습니다.');
    };

    const verifyToken = async token => {
      if (!token) return;
      setStatus('사람 확인 결과를 검증하는 중입니다.');
      if (!verifyEndpoint) {
        enableAfterCaptcha();
        return;
      }
      try {
        const resp = await fetch(verifyEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ provider, token })
        });
        const result = await resp.json();
        if (resp.ok && (result.success === true || result.ok === true || result.verified === true)) {
          enableAfterCaptcha();
        } else {
          captchaVerified = false;
          if (btn) btn.disabled = true;
          setStatus('사람 확인에 실패했습니다. 다시 시도해주세요.');
        }
      } catch (e) {
        captchaVerified = false;
        if (btn) btn.disabled = true;
        setStatus('검증 서버에 연결하지 못했습니다. 잠시 후 다시 시도해주세요.');
      }
    };

    const renderCaptcha = async () => {
      if (!captchaRequired || !captchaWrap || !captchaWidget || !btn) return;
      captchaWrap.hidden = false;
      btn.disabled = true;
      btn.textContent = '확인 완료 후 보기';
      setStatus('사람 확인을 완료해주세요.');

      try {
        if (provider === 'turnstile') {
          const turnstile = await loadExternalScript('https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit', 'turnstile');
          turnstile.render('#human-captcha-widget', {
            sitekey: siteKey,
            callback: token => verifyToken(token),
            'expired-callback': () => {
              captchaVerified = false;
              btn.disabled = true;
              setStatus('확인이 만료되었습니다. 다시 진행해주세요.');
            }
          });
        } else if (provider === 'recaptcha') {
          const grecaptcha = await loadExternalScript('https://www.google.com/recaptcha/api.js?render=explicit', 'grecaptcha');
          grecaptcha.render('human-captcha-widget', {
            sitekey: siteKey,
            callback: token => verifyToken(token),
            'expired-callback': () => {
              captchaVerified = false;
              btn.disabled = true;
              setStatus('확인이 만료되었습니다. 다시 진행해주세요.');
            }
          });
        }
      } catch (e) {
        setStatus('사람 확인 위젯을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.');
      }
    };

    if (isLikelyBot) {
      if (btn) {
        btn.disabled = true;
        btn.textContent = '자동화된 접근은 허용되지 않습니다';
      }
    } else {
      if (safeSessionGet(storageKey) === '1') unlock();
      else renderCaptcha();
      btn?.addEventListener('click', () => {
        if (!captchaVerified) {
          setStatus('사람 확인을 먼저 완료해주세요.');
          return;
        }
        unlock();
      });
    }

    ['copy', 'cut', 'dragstart'].forEach(type => {
      document.addEventListener(type, e => {
        if (!allowInteractiveTarget(e.target)) e.preventDefault();
      }, true);
    });
    document.addEventListener('contextmenu', e => {
      if (!allowInteractiveTarget(e.target)) e.preventDefault();
    }, true);
    document.addEventListener('keydown', e => {
      const key = (e.key || '').toLowerCase();
      if ((e.ctrlKey || e.metaKey) && ['c', 's', 'u', 'p'].includes(key) && !allowInteractiveTarget(e.target)) {
        e.preventDefault();
      }
    }, true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
