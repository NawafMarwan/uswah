#!/usr/bin/env python3
"""Login gate for the static site (GitHub Pages only, no server).

The real pages live in _src/ (plain; Jekyll never publishes "_" folders). This script

  * encrypts them with AES-256-GCM into assets/enc/*.bin, key = PBKDF2-SHA256(600k rounds) of
    "username\\0password"; the credentials come from the SITE_USER / SITE_PASSWORD secrets and are
    never written anywhere;
  * writes the small public wrapper pages (index.html, uswah.html, stats/, plan/, content_plan.html):
    a login form that fetches a blob, decrypts it in the browser and shows the page. The session lasts
    15 minutes; two minutes before the end a bar offers to extend it, otherwise the visitor is sent
    back to the login form.

    python3 scripts/protect.py                  # encrypt + wrappers (needs SITE_USER / SITE_PASSWORD)
    python3 scripts/protect.py --wrappers-only  # wrappers only (no secrets needed; blobs missing => "قيد الإعداد")

Optional testing variables: GATE_SESSION_SECONDS, GATE_WARN_SECONDS, GATE_ITER.
"""
import hashlib
import hmac
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "_src"
ENC = ROOT / "assets" / "enc"

SESSION_S = int(os.environ.get("GATE_SESSION_SECONDS") or 15 * 60)
WARN_S = int(os.environ.get("GATE_WARN_SECONDS") or 2 * 60)
ITER = int(os.environ.get("GATE_ITER") or 600_000)
SALT = hashlib.sha256(b"uswah-gate-v1").digest()[:16]  # public; only has to be unique to this site

# wrapper file -> (blob, path prefix back to the site root, script injected into <head> after decrypting)
PAGES = {
    "index.html": ("uswah", "", ""),
    "uswah.html": ("uswah", "", ""),
    "stats/index.html": ("uswah", "../", "window.__ROOT__='../';"),
    "plan/index.html": ("uswah", "../", "window.__ROOT__='../';window.__PAGE__='plan';"),
    "content_plan.html": ("content_plan", "", ""),
}
SOURCES = {"uswah": SRC / "uswah.html", "content_plan": SRC / "content_plan.html"}


def secret(user, password):
    user = unicodedata.normalize("NFC", user.strip().lower())
    return (user + "\0" + unicodedata.normalize("NFC", password)).encode("utf-8")


def logo_uri():
    m = re.search(r'--logo:url\("(data:image/png;base64,[^"]+)"\)', SOURCES["uswah"].read_text(encoding="utf-8"))
    return m.group(1) if m else ""


def encrypt_blobs(user, password):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = hashlib.pbkdf2_hmac("sha256", secret(user, password), SALT, ITER, 32)
    ENC.mkdir(parents=True, exist_ok=True)
    for name, src in SOURCES.items():
        plain = src.read_bytes()
        # Deterministic nonce (HMAC of the content): unchanged pages give byte-identical files, so the
        # repository does not grow when nothing changed; different content always gets a different nonce.
        iv = hmac.new(key, name.encode() + hashlib.sha256(plain).digest(), hashlib.sha256).digest()[:12]
        out = iv + AESGCM(key).encrypt(iv, plain, None)
        target = ENC / f"{name}.bin"
        if not target.exists() or target.read_bytes() != out:
            target.write_bytes(out)
        print(f"  ✓ {target.relative_to(ROOT)} ({len(out):,} bytes)")


WRAPPER = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="theme-color" content="#3a2236">
<title>مركز أسوة للسيرة النبوية — تسجيل الدخول</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cpath d='M8 60V30Q8 22 16 18L32 8l16 10q8 4 8 12v30' fill='none' stroke='%239a7c6a' stroke-width='6'/%3E%3Cpath d='M18 60V34q0-5 5-8l9-6 9 6q5 3 5 8v26' fill='none' stroke='%236e8fa3' stroke-width='6'/%3E%3C/svg%3E">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{color-scheme:light;--bg:#f8f1ec;--card:#fffaf6;--ink:#2e1c2b;--muted:#85737f;--line:#e5d6cb;--plum:#3a2236;--copper:#c2703d;--logo-filter:none}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#1b1118;--card:#2a1b28;--ink:#f6ece6;--muted:#a8949f;--line:#44303f;--plum:#4a2c45;--logo-filter:brightness(0) invert(.94)}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--ink);font-family:"IBM Plex Sans Arabic",system-ui,-apple-system,"Segoe UI",Tahoma,sans-serif;line-height:1.8;padding:20px}
.card{width:100%;max-width:400px;background:var(--card);border:1px solid var(--line);border-radius:24px;padding:30px 26px 26px;box-shadow:0 12px 40px -16px rgba(58,34,54,.35);text-align:center}
.logo{width:86px;height:94px;margin:0 auto 6px;background:url("__LOGO__") center/contain no-repeat;filter:var(--logo-filter)}
h1{margin:6px 0 2px;font-size:22px}
p.sub{margin:0 0 18px;color:var(--muted);font-size:14px}
label{display:block;text-align:start;font-size:13.5px;font-weight:600;margin:12px 0 4px}
input{width:100%;font:inherit;color:inherit;background:transparent;border:1px solid var(--line);border-radius:12px;padding:11px 14px;min-height:46px}
input:focus-visible{outline:2px solid var(--copper);outline-offset:1px}
button.go{width:100%;margin-top:18px;min-height:48px;border:0;border-radius:14px;background:var(--plum);color:#fffaf6;font:inherit;font-weight:700;font-size:16px;cursor:pointer}
button.go:disabled{opacity:.6;cursor:progress}
#msg{min-height:24px;margin-top:12px;font-size:14px;color:#b3412a;font-weight:600}
#msg.info{color:var(--muted);font-weight:500}
small{display:block;margin-top:14px;color:var(--muted);font-size:12.5px}
[hidden]{display:none!important}
</style>
</head>
<body>
<main class="card">
  <div class="logo" role="img" aria-label="شعار أسوة"></div>
  <h1>مركز أسوة للسيرة النبوية</h1>
  <p class="sub">هذا الموقع مخصص للمصرّح لهم. سجّل الدخول للمتابعة.</p>
  <form id="f" autocomplete="on">
    <label for="u">اسم المستخدم</label>
    <input id="u" name="username" autocomplete="username" autocapitalize="none" spellcheck="false" required>
    <label for="p">كلمة المرور</label>
    <input id="p" name="password" type="password" autocomplete="current-password" required>
    <button class="go" id="go" type="submit">دخول</button>
  </form>
  <div id="msg" role="status" aria-live="polite"></div>
  <small>تنتهي الجلسة بعد __SESSION_MIN__ دقيقة، وسيُعرض عليك تمديدها قبل ذلك.</small>
</main>
<script>
(() => {
'use strict';
const BLOB = __BLOB__, PREFIX = __PREFIX__, HEAD = __HEAD__;
const SALT = '__SALT__', ITER = __ITER__, SESSION = __SESSION_MS__, WARN = __WARN_MS__, KEY = 'uswah.gate';
const $ = s => document.querySelector(s);
const b64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
const toB64 = u => btoa(String.fromCharCode(...u));
const msg = (t, info) => { const m = $('#msg'); m.textContent = t || ''; m.className = info ? 'info' : ''; };
const store = {
  get() { try { return JSON.parse(sessionStorage.getItem(KEY)); } catch { return null; } },
  set(v) { try { sessionStorage.setItem(KEY, JSON.stringify(v)); } catch {} },
  del() { try { sessionStorage.removeItem(KEY); } catch {} },
};

let blobPromise;
const getBlob = () => blobPromise || (blobPromise = fetch(PREFIX + 'assets/enc/' + BLOB + '.bin', { cache: 'no-cache' })
  .then(r => r.ok ? r.arrayBuffer() : Promise.reject(new Error('missing'))).then(b => new Uint8Array(b)));

async function open(raw) {
  const data = await getBlob();
  const key = await crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['decrypt']);
  const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: data.slice(0, 12) }, key, data.slice(12));
  return new TextDecoder().decode(plain);
}
async function derive(user, pass) {
  const secret = new TextEncoder().encode(user.trim().toLowerCase().normalize('NFC') + '\0' + pass.normalize('NFC'));
  const base = await crypto.subtle.importKey('raw', secret, 'PBKDF2', false, ['deriveBits']);
  return new Uint8Array(await crypto.subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt: b64(SALT), iterations: ITER }, base, 256));
}

const TIMER = `<style>#gate-bar{position:fixed;z-index:99999;inset:auto 12px 12px 12px;max-width:460px;margin-inline:auto;display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:#3a2236;color:#fffaf6;padding:12px 16px;border-radius:16px;box-shadow:0 12px 40px -8px rgba(0,0,0,.5);font:600 14.5px/1.6 "IBM Plex Sans Arabic",system-ui,sans-serif}#gate-bar[hidden]{display:none}#gate-bar span{flex:1 1 180px}#gate-bar b{font-variant-numeric:tabular-nums;direction:ltr;unicode-bidi:isolate}#gate-bar button{font:inherit;border:0;border-radius:10px;padding:7px 14px;cursor:pointer;min-height:38px}#gate-x{background:#c2703d;color:#fff}#gate-o{background:rgba(255,255,255,.14);color:#fffaf6}</style>
<script>(function(){var KEY='${KEY}',SESSION=${SESSION},WARN=${WARN};
function get(){try{return JSON.parse(sessionStorage.getItem(KEY))}catch(e){return null}}
function leave(m){try{sessionStorage.removeItem(KEY);if(m)sessionStorage.setItem(KEY+'.msg',m)}catch(e){}location.reload()}
var bar=document.createElement('div');bar.id='gate-bar';bar.setAttribute('role','alert');bar.hidden=true;
bar.innerHTML='<span>ستنتهي جلستك خلال <b id="gate-t"></b></span><button id="gate-x" type="button">تمديد الجلسة</button><button id="gate-o" type="button">خروج</button>';
document.body.appendChild(bar);
var t=document.getElementById('gate-t');
function tick(){var s=get();if(!s||Date.now()>=s.exp){leave('انتهت الجلسة. سجّل الدخول مجددًا للمتابعة.');return}
var r=s.exp-Date.now();bar.hidden=r>WARN;if(r<=WARN){var q=Math.ceil(r/1000);t.textContent=Math.floor(q/60)+':'+('0'+q%60).slice(-2)}}
document.getElementById('gate-x').onclick=function(){var s=get();if(s){s.exp=Date.now()+SESSION;sessionStorage.setItem(KEY,JSON.stringify(s));tick()}};
document.getElementById('gate-o').onclick=function(){leave()};
setInterval(tick,1000);document.addEventListener('visibilitychange',tick);tick();
})();<\/script>`;

function show(html) {
  if (HEAD) html = html.replace('<head>', '<head>\n<script>' + HEAD + '<\/script>');
  html = html.replace(/<\/body>\s*<\/html>\s*$/i, TIMER + '</body></html>');
  document.open(); document.write(html); document.close();
}

async function enter(raw, fresh) {
  const html = await open(raw);
  if (fresh) store.set({ k: toB64(raw), exp: Date.now() + SESSION });
  show(html);
}

$('#f').addEventListener('submit', async e => {
  e.preventDefault();
  const go = $('#go'); go.disabled = true; msg('جارٍ التحقق…', true);
  try {
    const raw = await derive($('#u').value, $('#p').value);
    try { await enter(raw, true); }
    catch (err) {
      go.disabled = false;
      msg(err && err.message === 'missing' ? 'الموقع قيد الإعداد، حاول لاحقًا.' : 'اسم المستخدم أو كلمة المرور غير صحيحة.');
      $('#p').value = '';
    }
  } catch { go.disabled = false; msg('تعذّر التحقق من المتصفح. استخدم متصفحًا حديثًا.'); }
});

(async () => {
  try { const m = sessionStorage.getItem(KEY + '.msg'); if (m) { msg(m, true); sessionStorage.removeItem(KEY + '.msg'); } } catch {}
  const s = store.get();
  if (s && s.exp > Date.now()) {
    try { await enter(b64(s.k), false); return; } catch {}
  }
  store.del();
  $('#u').focus();
})();
})();
</script>
</body>
</html>
"""


def write_wrappers():
    logo = logo_uri()
    import base64
    salt_b64 = base64.b64encode(SALT).decode()
    for rel, (blob, prefix, head) in PAGES.items():
        html = (WRAPPER.replace("__LOGO__", logo).replace("__BLOB__", json.dumps(blob)).replace("__PREFIX__", json.dumps(prefix))
                .replace("__HEAD__", json.dumps(head)).replace("__SALT__", salt_b64).replace("__ITER__", str(ITER))
                .replace("__SESSION_MS__", str(SESSION_S * 1000)).replace("__WARN_MS__", str(WARN_S * 1000))
                .replace("__SESSION_MIN__", str(max(1, round(SESSION_S / 60)))))
        target = ROOT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_text(encoding="utf-8") != html:
            target.write_text(html, encoding="utf-8")
        print(f"  ✓ {rel}")


def main():
    if "--wrappers-only" not in sys.argv:
        user, password = os.environ.get("SITE_USER", "").strip(), os.environ.get("SITE_PASSWORD", "")
        if not user or len(password) < 8:
            sys.exit("SITE_USER / SITE_PASSWORD are missing (password: at least 8 characters). Pages were NOT re-encrypted.")
        for src in SOURCES.values():
            if not src.exists():
                sys.exit(f"missing {src}")
        encrypt_blobs(user, password)
    write_wrappers()


if __name__ == "__main__":
    main()
