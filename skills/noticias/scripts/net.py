"""Cliente HTTP resiliente e extração de texto e imagem das páginas das matérias.

Só usa a biblioteca padrão. Cada tentativa troca o User-Agent (e os cabeçalhos coerentes com
ele), respeita Retry-After, espaça as retentativas com backoff exponencial e, quando o servidor
barra o urllib pela assinatura TLS, tenta de novo pelo curl.
"""

import gzip
import html
import http.cookiejar
import json
import random
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections import defaultdict

FEED_ACCEPT = "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"
PAGE_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
IMAGE_ACCEPT = "image/avif,image/webp,image/jpeg,image/png,image/*;q=0.8"

# Navegadores reais, cada um com os cabeçalhos que ele de fato envia. Mandar sec-ch-ua do Chrome
# junto com um User-Agent do Firefox denuncia o robô para alguns firewalls.
_CHROME_CH = {"Sec-Ch-Ua-Mobile": "?0", "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
              "Sec-Fetch-Site": "none", "Upgrade-Insecure-Requests": "1"}
PROFILES = [
    {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/141.0.0.0 Safari/537.36",
     "Sec-Ch-Ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
     "Sec-Ch-Ua-Platform": '"macOS"', **_CHROME_CH},
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/141.0.0.0 Safari/537.36",
     "Sec-Ch-Ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
     "Sec-Ch-Ua-Platform": '"Windows"', **_CHROME_CH},
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
     "Sec-Ch-Ua": '"Microsoft Edge";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
     "Sec-Ch-Ua-Platform": '"Windows"', **_CHROME_CH},
    {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:144.0) Gecko/20100101 Firefox/144.0"},
    {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:144.0) Gecko/20100101 Firefox/144.0"},
    {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                   "Version/26.0 Safari/605.1.15"},
]

RETRY_STATUS = {403, 408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524}
# Página de desafio anti-robô servida com status 200 (Cloudflare, Akamai, captchas).
CHALLENGE = re.compile(rb"(<title>Just a moment|cf-chl-|challenge-platform|captcha-delivery|"
                       rb"<title>Access Denied</title>|Attention Required! \| Cloudflare)", re.I)
MAX_BACKOFF = 12.0
PER_HOST = 4  # requisições simultâneas por domínio, para não provocar 429

_host_locks = defaultdict(lambda: threading.BoundedSemaphore(PER_HOST))
_host_locks_guard = threading.Lock()
_stats_guard = threading.Lock()
STATS = defaultdict(int)  # contadores para o relatório da coleta


class Blocked(Exception):
    """O servidor respondeu, mas com um bloqueio (status ou página de desafio)."""

    def __init__(self, url, code, retry_after=None):
        super().__init__(f"HTTP {code} em {url}")
        self.code, self.retry_after = code, retry_after


def _count(key):
    with _stats_guard:
        STATS[key] += 1


def _host_sem(url):
    host = urllib.parse.urlsplit(url).hostname or ""
    with _host_locks_guard:
        return _host_locks[host]


def _headers(profile, accept):
    h = dict(profile)
    h.update({"Accept": accept, "Accept-Encoding": "gzip, deflate", "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6"})
    if accept != PAGE_ACCEPT:  # feeds e imagens não são navegação de documento
        for k in ("Sec-Fetch-Dest", "Sec-Fetch-Mode", "Upgrade-Insecure-Requests"):
            h.pop(k, None)
    return h


def _decode_body(data, encoding):
    if data[:2] == b"\x1f\x8b":
        return gzip.decompress(data)
    if encoding == "deflate":
        try:
            return zlib.decompress(data)
        except zlib.error:
            return zlib.decompress(data, -zlib.MAX_WBITS)
    return data


def _retry_after(value):
    try:
        return min(float(value), MAX_BACKOFF)
    except (TypeError, ValueError):
        return None


def _via_urllib(url, headers, timeout):
    # Jar novo por requisição: alguns sites devolvem um cookie e redirecionam para a própria URL.
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    try:
        resp = opener.open(urllib.request.Request(url, headers=headers), timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code in RETRY_STATUS:
            raise Blocked(url, e.code, _retry_after(e.headers.get("Retry-After"))) from None
        raise
    with resp:
        data = resp.read()
        return _decode_body(data, resp.headers.get("Content-Encoding")), resp.headers.get_content_charset()


def _via_curl(url, headers, timeout):
    cmd = ["curl", "-sSL", "--compressed", "-m", str(timeout), "-o", "-", "-w", "\n%{http_code}"]
    for k, v in headers.items():
        if k != "Accept-Encoding":  # o --compressed cuida disso
            cmd += ["-H", f"{k}: {v}"]
    out = subprocess.run(cmd + [url], capture_output=True, timeout=timeout + 5)
    if out.returncode != 0:
        raise OSError(f"curl saiu com código {out.returncode}: {out.stderr.decode(errors='replace').strip()[:120]}")
    body, _, code = out.stdout.rpartition(b"\n")
    code = int(code or 0)
    if code in RETRY_STATUS:
        raise Blocked(url, code)
    if code >= 400:
        raise urllib.error.HTTPError(url, code, "curl", None, None)
    return body, None


def http_get(url, timeout=20, accept=PAGE_ACCEPT, retries=3):
    """GET com retentativas. Devolve (bytes, charset) ou levanta a última exceção."""
    profiles = random.sample(PROFILES, len(PROFILES))
    has_curl = shutil.which("curl") is not None
    last = None
    with _host_sem(url):
        for attempt in range(retries + 1):
            headers = _headers(profiles[attempt % len(profiles)], accept)
            # Bloqueio persistente costuma ser pela assinatura TLS do urllib: alterna com o curl.
            use_curl = has_curl and isinstance(last, Blocked) and attempt % 2 == 1
            try:
                data, charset = (_via_curl if use_curl else _via_urllib)(url, headers, timeout)
                if accept == PAGE_ACCEPT and CHALLENGE.search(data[:20000]):
                    raise Blocked(url, "desafio anti-robô")
                if attempt:
                    _count("recuperadas após retentativa")
                return data, charset
            except urllib.error.HTTPError as e:  # 404, 410 etc.: não adianta insistir
                raise e
            except (Blocked, urllib.error.URLError, socket.timeout, ConnectionError, OSError,
                    subprocess.TimeoutExpired) as e:
                last = e
            if attempt < retries:
                _count("retentativas")
                wait = getattr(last, "retry_after", None) or min(MAX_BACKOFF, 0.8 * 2 ** attempt)
                time.sleep(wait + random.uniform(0, 0.5))
    _count("falhas definitivas")
    raise last


def get_page(url, timeout=20, retries=3):
    data, charset = http_get(url, timeout=timeout, retries=retries)
    m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", data[:4000], flags=re.I)
    enc = charset or (m[1].decode() if m else "utf-8")
    try:
        return data.decode(enc, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


# --- Extração -------------------------------------------------------------------

def clean(text):
    if not text:
        return ""
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.S)
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


BODY_MARKER = re.compile(
    r"class=\"[^\"]*(c-news__body|article-body|article__body|articleBody|post-content|entry-content|"
    r"materia-conteudo|news-body|content-body|single-content|texto-materia)[^\"]*\"",
    re.I,
)
BOILERPLATE = re.compile(
    r"(gostaria de receber|acesse seus artigos|minha folha|assine|assinante|newsletter|"
    r"copyright|todos os direitos|cadastre-se|faça login|clique aqui|leia também|siga o )",
    re.I,
)


def article_text(page):
    """Texto da matéria: articleBody do JSON-LD, parágrafos do corpo ou, por último, a descrição."""
    bodies = []
    for block in re.findall(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", page, flags=re.S | re.I):
        try:
            obj = json.loads(block, strict=False)
        except json.JSONDecodeError:
            continue
        stack = [obj]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                if isinstance(cur.get("articleBody"), str):
                    bodies.append(cur["articleBody"])
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
    text = clean(max(bodies, key=len)) if bodies else ""

    if len(text) < 400:
        stripped = re.sub(r"<(script|style|nav|header|footer|aside|form|figure)\b.*?</\1>", " ",
                          page, flags=re.S | re.I)
        # Globo (O Globo, Valor, g1) marca os parágrafos da matéria com essa classe.
        globo = re.findall(r"<p\b[^>]*class=\"[^\"]*content-text__container[^\"]*\"[^>]*>(.*?)</p>",
                           stripped, flags=re.S | re.I)
        if globo:
            raw_paras = globo
        else:
            m = BODY_MARKER.search(stripped)
            raw_paras = re.findall(r"<p\b[^>]*>(.*?)</p>", stripped[m.start():] if m else stripped,
                                   flags=re.S | re.I)
        paras, seen = [], set()
        for p in map(clean, raw_paras):
            if len(p) > 60 and p not in seen and not BOILERPLATE.search(p):
                seen.add(p)
                paras.append(p)
        alt = " ".join(paras)
        if len(alt) > len(text):
            text = alt
    if not text:
        m = re.search(r"<meta[^>]+(?:property|name)=[\"'](?:og:)?description[\"'][^>]+content=[\"']([^\"']+)",
                      page, flags=re.I)
        text = clean(m[1]) if m else ""
    return text


def page_image(page, url):
    """og:image (ou twitter:image) e o texto alternativo da página da matéria."""
    tags = {}
    for tag in re.findall(r"<meta\b[^>]*>", page[:200000], flags=re.I):
        attrs = dict((k.lower(), html.unescape(v)) for k, v in re.findall(r"([\w:-]+)\s*=\s*[\"']([^\"']*)[\"']", tag))
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key and "content" in attrs:
            tags.setdefault(key, attrs["content"])
    src = tags.get("og:image:secure_url") or tags.get("og:image") or tags.get("twitter:image") or ""
    alt = tags.get("og:image:alt") or tags.get("twitter:image:alt") or ""
    return (urllib.parse.urljoin(url, src) if src else ""), alt
