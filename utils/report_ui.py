"""Shared building blocks for the downloadable HTML reports.

Reports are self-contained single files: no external resources (the CSP only
allows inline styles/scripts), all report data is embedded as JSON and rendered
on the client with DOM APIs (textContent / setAttribute only, never innerHTML
with data), so user-controlled values cannot inject markup.
"""

import html
import json
import os
import re
import urllib.parse
from datetime import datetime

# Fixed-length masking used across reports (same values as the legacy report).
MASK_TOTAL_LENGTH = 16
MASK_PREFIX_LENGTH = 4

_CONTROL_CHARS = re.compile(r"[\x00-\x20\x7f]")


def esc(value) -> str:
    """HTML-escape a value for direct insertion into markup."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def mask_secret(value: str) -> str:
    value = value or ""
    if len(value) > MASK_PREFIX_LENGTH:
        return value[:MASK_PREFIX_LENGTH] + "*" * (MASK_TOTAL_LENGTH - MASK_PREFIX_LENGTH)
    return value + "*" * max(MASK_TOTAL_LENGTH - len(value), 0)


def safe_href(url) -> str:
    """Return the URL if it is a plain http(s) link, otherwise an empty string."""
    if not url:
        return ""
    url = str(url).strip()
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return ""
    # Encode anything unusual but keep existing %-escapes intact.
    url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~")
    if _CONTROL_CHARS.search(url):
        return ""
    return url


def format_dt(value, fmt="%d.%m.%Y %H:%M") -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime(fmt)
    try:
        return datetime.fromisoformat(str(value)).strftime(fmt)
    except ValueError:
        return str(value)


def format_duration(started, completed) -> str:
    if not started or not completed:
        return ""
    try:
        seconds = int((completed - started).total_seconds())
    except Exception:
        return ""
    if seconds < 0:
        return ""
    if seconds < 60:
        return f"{seconds} с"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} мин {sec} с"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} ч {minutes} мин"


def display_path(path: str) -> str:
    path = (path or "").replace("\\", "/").replace("/devzone_repository/", "/")
    return path.lstrip("/")


def split_path(path: str):
    """Return (directory, filename, component, extension) for a display path."""
    directory, filename = os.path.split(path)
    component = path.split("/", 1)[0] if "/" in path else "(корень)"
    name_lower = filename.lower()
    if "." in name_lower.lstrip("."):
        extension = "." + name_lower.rsplit(".", 1)[1]
    elif name_lower.startswith("."):
        extension = name_lower
    else:
        extension = "(без расширения)"
    return directory, filename, component, extension


def embed_json(data) -> str:
    """Serialize data for a <script type="application/json"> block."""
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def copy_value_html(value: str, label: str, shown: str = None) -> str:
    """Value with a copy button on the same line (long values are ellipsized)."""
    if not value:
        return ""
    return (
        f'<span class="val-copy"><span class="val mono" title="{esc(value)}">{esc(shown or value)}</span>'
        f'<span data-copy="{esc(value)}" data-copy-label="{esc(label)}"></span></span>'
    )


def meta_item(label: str, value_html: str, mono: bool = False) -> str:
    if not value_html:
        return ""
    cls = "meta-value mono" if mono else "meta-value"
    return f'<div class="meta-item"><dt>{esc(label)}</dt><dd class="{cls}">{value_html}</dd></div>'


def kpi(label: str, value, hint: str = "", tone: str = "", filter_spec: str = "") -> str:
    attrs = ""
    tag = "div"
    if filter_spec:
        tag = "button"
        attrs = f' type="button" data-filter="{esc(filter_spec)}" title="Показать в списке"'
    tone_cls = f" kpi-{tone}" if tone else ""
    hint_html = f'<span class="kpi-hint">{esc(hint)}</span>' if hint else ""
    return (
        f'<{tag} class="kpi{tone_cls}"{attrs}>'
        f'<span class="kpi-label">{esc(label)}</span>'
        f'<span class="kpi-value">{esc(value)}</span>{hint_html}</{tag}>'
    )


ICONS = {
    "pass": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="m8.5 12 2.5 2.5 4.5-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "fail": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M12 7.5v5.5M12 16.2v.3" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
    "warn": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M12 8v4.5M12 15.8v.3" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
}


def verdict_block(tone: str, title: str, text: str) -> str:
    icon = ICONS.get({"success": "pass", "danger": "fail"}.get(tone, "warn"))
    return (
        f'<div class="verdict verdict-{tone}" role="status">'
        f'<span class="verdict-icon">{icon}</span>'
        f'<div><div class="verdict-label">Итоговый статус</div>'
        f'<div class="verdict-title">{esc(title)}</div>'
        f'<div class="verdict-text">{esc(text)}</div></div></div>'
    )


REPORT_CSS = r"""
:root{
  --bg:#f4f6f8;--surface:#fff;--surface-2:#f8fafc;--surface-3:#eef2f6;
  --text:#18202a;--text-2:#4a5565;--text-3:#7a8594;
  --border:#dde3ea;--border-strong:#c5cdd8;
  --accent:#2f5bd3;--accent-weak:#e8eefc;--focus:rgba(47,91,211,.35);
  --crit:#b42318;--crit-bg:#fdecea;--crit-border:#f5c2bd;
  --high:#c2410c;--high-bg:#fff1e6;--high-border:#fcd2b2;
  --med:#a15c00;--med-bg:#fff6dd;--med-border:#f5dc9c;
  --low:#3f6212;--low-bg:#eef7e1;--low-border:#cfe5ad;
  --ok:#1a7f45;--ok-bg:#e7f6ed;--ok-border:#b4e1c5;
  --muted-bg:#eef1f4;--muted-border:#d7dde4;
  --code-bg:#f6f8fa;--hl-bg:#fff4c2;
  --shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.04);
  --radius:10px;--radius-sm:6px;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  color-scheme:light;
}
/* Dark theme: follows the OS unless the viewer picked a theme (data-theme on <html>). */
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#0f141a;--surface:#161c24;--surface-2:#1b222c;--surface-3:#222b36;
    --text:#e6ebf1;--text-2:#b3bdca;--text-3:#8592a3;
    --border:#2a3441;--border-strong:#394555;
    --accent:#7aa2ff;--accent-weak:#1f2a44;--focus:rgba(122,162,255,.4);
    --crit:#ff8a80;--crit-bg:#3a1c1c;--crit-border:#5c2b2b;
    --high:#ffa66b;--high-bg:#3a2514;--high-border:#5a3a20;
    --med:#f2c04f;--med-bg:#352a10;--med-border:#55441b;
    --low:#a7d36b;--low-bg:#1f2c14;--low-border:#344a22;
    --ok:#6fd49a;--ok-bg:#15301f;--ok-border:#22472f;
    --muted-bg:#232b35;--muted-border:#323d4a;
    --code-bg:#121820;--hl-bg:#3d3514;
    --shadow:none;color-scheme:dark;
  }
}
:root[data-theme="dark"]{
    --bg:#0f141a;--surface:#161c24;--surface-2:#1b222c;--surface-3:#222b36;
    --text:#e6ebf1;--text-2:#b3bdca;--text-3:#8592a3;
    --border:#2a3441;--border-strong:#394555;
    --accent:#7aa2ff;--accent-weak:#1f2a44;--focus:rgba(122,162,255,.4);
    --crit:#ff8a80;--crit-bg:#3a1c1c;--crit-border:#5c2b2b;
    --high:#ffa66b;--high-bg:#3a2514;--high-border:#5a3a20;
    --med:#f2c04f;--med-bg:#352a10;--med-border:#55441b;
    --low:#a7d36b;--low-bg:#1f2c14;--low-border:#344a22;
    --ok:#6fd49a;--ok-bg:#15301f;--ok-border:#22472f;
    --muted-bg:#232b35;--muted-border:#323d4a;
    --code-bg:#121820;--hl-bg:#3d3514;
    --shadow:none;color-scheme:dark;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
button{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.mono{font-family:var(--mono);font-size:12.5px}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
svg{width:16px;height:16px;flex:none}

.topbar{background:var(--surface);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:20}
.topbar-inner{max-width:1320px;margin:0 auto;padding:10px 24px;display:flex;align-items:center;gap:12px}
.brand{display:flex;align-items:center;gap:8px;font-weight:600}
.brand-mark{width:22px;height:22px;border-radius:6px;background:var(--text);color:var(--surface);display:grid;place-items:center}
.brand-mark svg{width:14px;height:14px}
.brand-sub{color:var(--text-3);font-weight:400}
.topbar-spacer{flex:1}
.btn{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--border);background:var(--surface);border-radius:var(--radius-sm);padding:6px 12px;cursor:pointer;white-space:nowrap;line-height:1.3}
.btn:hover{background:var(--surface-3)}
.btn[aria-pressed="true"],.btn.is-active{border-color:var(--accent);background:var(--accent-weak);color:var(--accent)}
.btn-ghost{border-color:transparent;background:transparent}
.btn-sm{padding:3px 8px;font-size:12.5px}
.btn-icon{padding:4px 6px}
.btn-icon svg{width:16px;height:16px}
.btn .count{background:var(--accent);color:#fff;border-radius:999px;padding:0 6px;font-size:11px;line-height:16px}

.page{max-width:1320px;margin:0 auto;padding:24px 24px 48px}
.section{margin-top:24px}
.section-head{display:flex;align-items:baseline;gap:12px;margin:0 0 12px}
.section-head h2{font-size:16px;margin:0}
.section-head .sub{color:var(--text-3)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow)}

.overview{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:16px}
.scan-card{padding:20px 22px}
.eyebrow{color:var(--text-3);font-size:12px;text-transform:uppercase;letter-spacing:.06em;font-weight:600}
.scan-title{font-size:22px;line-height:1.25;margin:4px 0 2px;word-break:break-word}
.scan-repo{color:var(--text-2);word-break:break-all}
.meta{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px 24px;margin:18px 0 0;padding:16px 0 0;border-top:1px solid var(--border)}
.meta-item{min-width:0}
.meta-item dt{color:var(--text-3);font-size:12px;margin-bottom:2px}
.meta-item dd{margin:0;word-break:break-all}
.copy{border:0;background:none;padding:2px;margin-left:4px;cursor:pointer;color:var(--text-3);vertical-align:-3px;border-radius:4px}
.copy:hover{color:var(--accent);background:var(--surface-3)}
.copy svg{width:14px;height:14px}
.val-copy{display:inline-flex;align-items:center;max-width:100%;min-width:0;vertical-align:top}
.val-copy .val{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.val-copy .copy{flex:none;margin-left:4px;vertical-align:0}

.overview-side{display:flex;flex-direction:column;gap:12px;min-width:0}
.verdict{display:flex;gap:14px;padding:20px;border-radius:var(--radius);border:1px solid;flex:1 0 auto}
.triage{padding:14px 16px}
.triage-head{display:flex;justify-content:space-between;gap:8px}
.verdict-icon svg{width:36px;height:36px}
.verdict-label{font-size:12px;text-transform:uppercase;letter-spacing:.06em;font-weight:600;opacity:.85}
.verdict-title{font-size:20px;font-weight:700;margin:2px 0 4px;line-height:1.2}
.verdict-text{color:var(--text-2)}
.verdict-danger{background:var(--crit-bg);border-color:var(--crit-border);color:var(--crit)}
.verdict-warning{background:var(--med-bg);border-color:var(--med-border);color:var(--med)}
.verdict-success{background:var(--ok-bg);border-color:var(--ok-border);color:var(--ok)}

.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:16px}
.kpi{display:flex;flex-direction:column;align-items:flex-start;text-align:left;gap:2px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:12px 14px;box-shadow:var(--shadow);position:relative;overflow:hidden}
.kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:transparent}
button.kpi{cursor:pointer}
button.kpi:hover{border-color:var(--border-strong);background:var(--surface-2)}
.kpi-label{color:var(--text-2);font-size:12.5px}
.kpi-value{font-size:24px;font-weight:700;line-height:1.2;font-variant-numeric:tabular-nums}
.kpi-hint{color:var(--text-3);font-size:12px}
.kpi-crit::before{background:var(--crit)}.kpi-crit .kpi-value{color:var(--crit)}
.kpi-high::before{background:var(--high)}
.kpi-med::before{background:var(--med)}
.kpi-ok::before{background:var(--ok)}
.kpi-muted .kpi-value{color:var(--text-3)}

.progress-bar{display:flex;height:8px;border-radius:999px;overflow:hidden;background:var(--surface-3)}
.progress-bar span{display:block;height:100%}
.progress-legend{display:flex;flex-wrap:wrap;gap:4px 16px;margin-top:8px;color:var(--text-2);font-size:12.5px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:1px}

.findings{padding:0;overflow:visible}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:12px 14px;border-bottom:1px solid var(--border)}
.search{position:relative;flex:1 1 280px;min-width:220px}
.search svg{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--text-3)}
.search input{width:100%;padding:7px 34px 7px 32px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface);color:var(--text);font:inherit}
.search input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--focus)}
.search kbd{position:absolute;right:8px;top:50%;transform:translateY(-50%);font:11px var(--mono);color:var(--text-3);border:1px solid var(--border);border-radius:4px;padding:0 5px}
.facet{position:relative}
.facet-btn svg{width:12px;height:12px;color:var(--text-3)}
.popover{position:absolute;top:calc(100% + 6px);left:0;z-index:30;width:280px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);box-shadow:0 10px 30px rgba(16,24,40,.16);padding:8px;display:none}
.popover.open{display:block}
.popover-search{width:100%;padding:6px 8px;border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:6px;background:var(--surface);color:var(--text);font:inherit}
.popover-list{max-height:280px;overflow:auto}
.opt{display:flex;align-items:center;gap:8px;padding:5px 6px;border-radius:var(--radius-sm);cursor:pointer}
.opt:hover{background:var(--surface-2)}
.opt input{margin:0;accent-color:var(--accent)}
.opt-label{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.opt-count{color:var(--text-3);font-variant-numeric:tabular-nums;font-size:12px}
.popover-foot{display:flex;justify-content:space-between;border-top:1px solid var(--border);margin-top:6px;padding-top:6px}
.sort select{padding:6px 8px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface);color:var(--text);font:inherit}
.chips{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:8px 14px;border-bottom:1px solid var(--border);background:var(--surface-2)}
.chips:empty{display:none}
.chip{display:inline-flex;align-items:center;gap:4px;border:1px solid var(--border);background:var(--surface);border-radius:999px;padding:2px 4px 2px 10px;font-size:12.5px}
.chip b{font-weight:600}
.chip button{border:0;background:none;cursor:pointer;color:var(--text-3);display:grid;place-items:center;padding:2px;border-radius:50%}
.chip button:hover{background:var(--surface-3);color:var(--text)}
.chip button svg{width:12px;height:12px}
.result-line{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;padding:10px 14px;color:var(--text-2);font-size:13px;border-bottom:1px solid var(--border)}
.result-line .spacer{flex:1}
.notice{display:inline-flex;gap:6px;align-items:center;color:var(--text-2)}
.link-btn{border:0;background:none;color:var(--accent);cursor:pointer;padding:0}
.link-btn:hover{text-decoration:underline}

.table-wrap{overflow-x:auto}
table.grid{width:100%;border-collapse:collapse}
.grid th{position:sticky;top:0;text-align:left;font-size:12px;font-weight:600;color:var(--text-3);text-transform:uppercase;letter-spacing:.04em;padding:8px 12px;border-bottom:1px solid var(--border);background:var(--surface-2);white-space:nowrap}
.grid td{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:top}
.grid tr.row{cursor:pointer}
.grid tr.row:hover td{background:var(--surface-2)}
.grid tr.row[aria-expanded="true"] td{background:var(--surface-2);border-bottom-color:transparent}
.grid tr.row.is-muted td{color:var(--text-3)}
.grid tr.row.is-muted .sev{opacity:.6}
.col-chev{width:28px;padding-right:0!important;color:var(--text-3)}
.col-chev svg{transition:transform .15s}
tr[aria-expanded="true"] .col-chev svg{transform:rotate(90deg)}
.loc-file{font-weight:600;word-break:break-all}
.loc-dir{color:var(--text-3);font-size:12.5px;word-break:break-all}
.loc-line{color:var(--text-3);font-family:var(--mono);font-size:12px}
.secret-mask{font-family:var(--mono);font-size:12.5px;background:var(--code-bg);border:1px solid var(--border);border-radius:4px;padding:1px 6px;white-space:nowrap}
.type-name{font-weight:500}
.sub-text{color:var(--text-3);font-size:12.5px}

.sev{display:inline-flex;align-items:center;gap:6px;font-weight:600;font-size:12.5px;padding:2px 8px 2px 6px;border-radius:var(--radius-sm);border:1px solid;white-space:nowrap}
.sev::before{content:"";width:8px;height:8px;border-radius:2px;background:currentColor}
.sev-crit{color:var(--crit);background:var(--crit-bg);border-color:var(--crit-border)}
.sev-high{color:var(--high);background:var(--high-bg);border-color:var(--high-border)}
.sev-med{color:var(--med);background:var(--med-bg);border-color:var(--med-border)}
.sev-low{color:var(--low);background:var(--low-bg);border-color:var(--low-border)}
.sev-none{color:var(--text-2);background:var(--muted-bg);border-color:var(--muted-border)}

.st{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;white-space:nowrap}
.st::before{content:"";width:8px;height:8px;border-radius:50%;border:2px solid currentColor;box-sizing:border-box}
.st-confirmed{color:var(--crit)}
.st-confirmed::before{background:currentColor}
.st-open{color:var(--text-2)}
.st-refuted{color:var(--ok)}
.st-refuted::before{background:currentColor}
.st-date{display:block;color:var(--text-3);font-size:12px;margin-left:14px}

.tag{display:inline-block;font-size:12px;padding:1px 7px;border-radius:999px;background:var(--muted-bg);border:1px solid var(--muted-border);color:var(--text-2);white-space:nowrap}

tr.detail td{padding:0 12px 16px 40px;background:var(--surface-2)}
.detail-grid{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:16px;align-items:start}
.detail-box{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm)}
.detail-box h4{margin:0;padding:8px 12px;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
.kv{display:grid;grid-template-columns:120px minmax(0,1fr);gap:6px 10px;padding:10px 12px;margin:0}
.kv dt{color:var(--text-3)}
.kv dd{margin:0;word-break:break-all}
.kv-2{grid-template-columns:130px minmax(0,1fr) 130px minmax(0,1fr);gap:8px 14px}
.detail-actions{display:flex;flex-wrap:wrap;gap:8px;padding:10px 12px;border-top:1px solid var(--border)}
.reasons{margin:0;padding:10px 12px 10px 28px}
.reasons li{margin:2px 0}
.callout{padding:10px 12px;border-bottom:1px solid var(--border);background:var(--ok-bg);color:var(--text)}
.callout b{color:var(--ok)}

.more{display:flex;justify-content:center;gap:8px;padding:14px}
.empty{padding:48px 16px;text-align:center;color:var(--text-2)}
.empty h3{margin:8px 0 4px;color:var(--text);font-size:16px}
.empty svg{width:40px;height:40px;color:var(--ok)}
.empty.filtered svg{color:var(--text-3)}

.footer{max-width:1320px;margin:0 auto;padding:0 24px 32px;color:var(--text-3);font-size:12.5px;display:flex;flex-wrap:wrap;gap:6px 24px;justify-content:space-between}
.footer .warn{display:inline-flex;gap:6px;align-items:center}

@media (max-width:960px){
  .overview{grid-template-columns:1fr}
  .detail-grid{grid-template-columns:1fr}
  .kv-2{grid-template-columns:130px minmax(0,1fr)}
}
@media (max-width:640px){
  .page{padding:16px}
  .topbar-inner{padding:10px 16px}
  .brand-sub{display:none}
  .grid .col-hide-sm{display:none}
  tr.detail td{padding-left:12px}
  tr.detail td > *{position:sticky;left:12px;max-width:calc(100vw - 58px)}
}
@media print{
  :root{color-scheme:light}
  body{background:#fff;font-size:12px}
  .topbar,.toolbar,.more,.copy,.facet,.detail-actions,.no-print{display:none!important}
  .card,.kpi{box-shadow:none}
  .grid th{position:static}
  .grid tr{break-inside:avoid}
  .page{padding:0;max-width:none}
}
"""


# Generic client-side engine. A page defines `window.ReportSchema` before it runs.
REPORT_CORE_JS = r"""
(function () {
  'use strict';
  var S = window.ReportSchema;
  var dataNode = document.getElementById('report-data');
  if (!S || !dataNode) return;
  var DATA = JSON.parse(dataNode.textContent || '{}');
  var ITEMS = DATA.items || [];
  var PAGE = 100;

  var ICON = {
    chevron: '<svg viewBox="0 0 16 16"><path d="m6 4 4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    down: '<svg viewBox="0 0 16 16"><path d="m4 6 4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    x: '<svg viewBox="0 0 16 16"><path d="m4 4 8 8M12 4l-8 8" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
    copy: '<svg viewBox="0 0 16 16"><rect x="5.5" y="5.5" width="8" height="8" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M10.5 3.5v-.5A1.5 1.5 0 0 0 9 1.5H3A1.5 1.5 0 0 0 1.5 3v6A1.5 1.5 0 0 0 3 10.5h.5" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>',
    ext: '<svg viewBox="0 0 16 16"><path d="M9 2.5h4.5V7M13.5 2.5 7.5 8.5M12 9.5V13a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h3.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    ok: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="m8 12.5 2.8 2.8L16.5 9.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    search: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="m16 16 4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>'
  };

  // ---------- DOM helper ----------
  function h(tag, attrs) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === 'class') node.className = v;
        else if (k === 'text') node.textContent = v;
        else if (k === 'icon') node.insertAdjacentHTML('afterbegin', ICON[v] || '');
        else if (k.slice(0, 2) === 'on') node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v === true ? '' : String(v));
      });
    }
    for (var i = 2; i < arguments.length; i++) append(node, arguments[i]);
    return node;
  }
  function append(node, child) {
    if (child === null || child === undefined || child === false) return;
    if (Array.isArray(child)) { child.forEach(function (c) { append(node, c); }); return; }
    node.appendChild(typeof child === 'object' ? child : document.createTextNode(String(child)));
  }
  function plural(n, one, few, many) {
    var m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  }
  function copyText(text, btn) {
    function done() {
      if (!btn) return;
      var prev = btn.getAttribute('title');
      btn.setAttribute('title', 'Скопировано');
      btn.classList.add('is-active');
      setTimeout(function () { btn.setAttribute('title', prev || 'Копировать'); btn.classList.remove('is-active'); }, 1200);
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else fallback();
    function fallback() {
      var ta = h('textarea', { style: 'position:fixed;opacity:0' });
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch (e) { /* ignore */ }
      ta.remove();
    }
  }
  function copyBtn(text, label) {
    var b = h('button', { type: 'button', class: 'copy', title: label || 'Копировать', 'aria-label': label || 'Копировать', icon: 'copy' });
    b.addEventListener('click', function (e) { e.stopPropagation(); copyText(text, b); });
    return b;
  }
  var helpers = { h: h, copyBtn: copyBtn, copyText: copyText, plural: plural, icon: ICON };

  // Static copy buttons rendered server-side.
  document.querySelectorAll('[data-copy]').forEach(function (el) {
    var b = copyBtn(el.getAttribute('data-copy'), el.getAttribute('data-copy-label'));
    el.replaceWith(b);
  });
  // Value + copy icon kept on one line; long values are ellipsized, full value in the tooltip.
  function copyValue(value, label, shown) {
    return h('span', { class: 'val-copy' }, h('span', { class: 'val mono', title: value, text: shown || value }), copyBtn(value, label));
  }
  helpers.copyValue = copyValue;

  // ---------- facets ----------
  var facets = S.facets.map(function (f) {
    var counts = {};
    ITEMS.forEach(function (it) { var v = f.get(it); counts[v] = (counts[v] || 0) + 1; });
    var values = Object.keys(counts);
    var order = f.order || [];
    values.sort(function (a, b) {
      var ia = order.indexOf(a), ib = order.indexOf(b);
      if (ia !== -1 || ib !== -1) return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
      return counts[b] - counts[a] || a.localeCompare(b);
    });
    return { def: f, key: f.key, values: values, total: counts };
  });
  var facetByKey = {};
  facets.forEach(function (f) { facetByKey[f.key] = f; });
  function labelOf(f, v) { return (f.def.labels && f.def.labels[v]) || v; }

  var state = { sel: {}, q: '', sort: S.sorts[0].key, shown: PAGE, open: {} };
  function defaultSelection(f) {
    var hidden = f.def.hiddenByDefault || [];
    var keep = f.values.filter(function (v) { return hidden.indexOf(v) === -1; });
    // If everything would be hidden, show it all instead of an empty report.
    return new Set(keep.length ? keep : f.values);
  }
  function resetAll() {
    facets.forEach(function (f) { state.sel[f.key] = defaultSelection(f); });
    state.q = ''; if (searchInput) searchInput.value = '';
    state.shown = PAGE;
  }
  function isFiltered(f) { return state.sel[f.key].size !== f.values.length; }

  function matches(it, skipKey) {
    for (var i = 0; i < facets.length; i++) {
      var f = facets[i];
      if (f.key === skipKey) continue;
      if (!state.sel[f.key].has(f.def.get(it))) return false;
    }
    if (state.q) {
      if (!it.__s) it.__s = S.searchText(it).toLowerCase();
      var terms = state.q.split(/\s+/);
      for (var j = 0; j < terms.length; j++) if (terms[j] && it.__s.indexOf(terms[j]) === -1) return false;
    }
    return true;
  }

  // ---------- toolbar ----------
  var root = document.getElementById('findings');
  var toolbar = h('div', { class: 'toolbar', role: 'search' });
  var searchInput = h('input', { type: 'search', placeholder: S.searchPlaceholder || 'Поиск', 'aria-label': 'Поиск по находкам', autocomplete: 'off', spellcheck: 'false' });
  toolbar.appendChild(h('label', { class: 'search' }, h('span', { icon: 'search' }), searchInput, h('kbd', { text: '/' })));
  var debounce;
  searchInput.addEventListener('input', function () {
    clearTimeout(debounce);
    debounce = setTimeout(function () { state.q = searchInput.value.trim().toLowerCase(); state.shown = PAGE; render(); }, 120);
  });

  var popovers = [];
  facets.forEach(function (f) {
    if (f.values.length < 1) return;
    var wrap = h('div', { class: 'facet' });
    var btn = h('button', { type: 'button', class: 'btn facet-btn', 'aria-haspopup': 'true', 'aria-expanded': 'false' });
    var pop = h('div', { class: 'popover', role: 'dialog', 'aria-label': f.def.label });
    var list = h('div', { class: 'popover-list' });
    var filterInput = null;
    if (f.values.length > 8) {
      filterInput = h('input', { class: 'popover-search', type: 'search', placeholder: 'Найти значение…', 'aria-label': 'Найти значение' });
      filterInput.addEventListener('input', function () { fillList(); });
      pop.appendChild(filterInput);
    }
    pop.appendChild(list);
    pop.appendChild(h('div', { class: 'popover-foot' },
      h('button', { type: 'button', class: 'link-btn', text: 'Все', onclick: function () { state.sel[f.key] = new Set(f.values); state.shown = PAGE; render(); } }),
      h('button', { type: 'button', class: 'link-btn', text: 'Ни одного', onclick: function () { state.sel[f.key] = new Set(); state.shown = PAGE; render(); } }),
      (f.def.hiddenByDefault || []).length ? h('button', { type: 'button', class: 'link-btn', text: 'По умолчанию', onclick: function () { state.sel[f.key] = defaultSelection(f); state.shown = PAGE; render(); } }) : null
    ));
    function fillList() {
      list.textContent = '';
      var term = filterInput ? filterInput.value.trim().toLowerCase() : '';
      var live = {};
      ITEMS.forEach(function (it) { if (matches(it, f.key)) { var v = f.def.get(it); live[v] = (live[v] || 0) + 1; } });
      f.values.forEach(function (v) {
        var label = labelOf(f, v);
        if (term && label.toLowerCase().indexOf(term) === -1) return;
        var cb = h('input', { type: 'checkbox' });
        cb.checked = state.sel[f.key].has(v);
        cb.addEventListener('change', function () {
          if (cb.checked) state.sel[f.key].add(v); else state.sel[f.key].delete(v);
          state.shown = PAGE; render();
        });
        var swatch = f.def.swatch ? f.def.swatch(v) : null;
        list.appendChild(h('label', { class: 'opt' }, cb, swatch, h('span', { class: 'opt-label', title: label, text: label }), h('span', { class: 'opt-count', text: (live[v] || 0) + ' / ' + f.total[v] })));
      });
      if (!list.childNodes.length) list.appendChild(h('div', { class: 'opt sub-text', text: 'Ничего не найдено' }));
    }
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var willOpen = !pop.classList.contains('open');
      closePopovers();
      if (willOpen) { fillList(); pop.classList.add('open'); btn.setAttribute('aria-expanded', 'true'); if (filterInput) filterInput.focus(); }
    });
    pop.addEventListener('click', function (e) { e.stopPropagation(); });
    wrap.appendChild(btn); wrap.appendChild(pop);
    toolbar.appendChild(wrap);
    popovers.push({ f: f, btn: btn, pop: pop, fill: fillList });
  });
  function closePopovers() {
    popovers.forEach(function (p) { p.pop.classList.remove('open'); p.btn.setAttribute('aria-expanded', 'false'); });
  }
  document.addEventListener('click', closePopovers);

  var sortSel = h('select', { 'aria-label': 'Сортировка' });
  S.sorts.forEach(function (s) { sortSel.appendChild(h('option', { value: s.key, text: s.label })); });
  sortSel.addEventListener('change', function () { state.sort = sortSel.value; render(); });
  toolbar.appendChild(h('label', { class: 'sort' }, h('span', { class: 'sr-only', text: 'Сортировка' }), sortSel));

  var chips = h('div', { class: 'chips', 'aria-label': 'Активные фильтры' });
  var resultLine = h('div', { class: 'result-line', 'aria-live': 'polite' });
  var table = h('table', { class: 'grid' });
  var thead = h('thead'), tbody = h('tbody');
  var headRow = h('tr', null, h('th', { class: 'col-chev' }, h('span', { class: 'sr-only', text: 'Подробнее' })));
  S.columns.forEach(function (c) { headRow.appendChild(h('th', { class: c.className || null, text: c.label })); });
  thead.appendChild(headRow); table.appendChild(thead); table.appendChild(tbody);
  var more = h('div', { class: 'more no-print' });
  var emptyBox = h('div');

  root.appendChild(toolbar);
  root.appendChild(chips);
  root.appendChild(resultLine);
  root.appendChild(h('div', { class: 'table-wrap' }, table));
  root.appendChild(emptyBox);
  root.appendChild(more);

  // ---------- rendering ----------
  function sorted(list) {
    var s = S.sorts.filter(function (x) { return x.key === state.sort; })[0] || S.sorts[0];
    return list.slice().sort(s.cmp);
  }

  function renderChips() {
    chips.textContent = '';
    facets.forEach(function (f) {
      if (!isFiltered(f)) return;
      var vals = f.values.filter(function (v) { return state.sel[f.key].has(v); }).map(function (v) { return labelOf(f, v); });
      var text = vals.length === 0 ? 'ничего' : (vals.length > 3 ? vals.slice(0, 3).join(', ') + ' +' + (vals.length - 3) : vals.join(', '));
      chips.appendChild(h('span', { class: 'chip' }, h('span', null, f.def.label + ': ', h('b', { text: text })),
        h('button', { type: 'button', title: 'Снять фильтр', 'aria-label': 'Снять фильтр ' + f.def.label, icon: 'x', onclick: function () { state.sel[f.key] = new Set(f.values); state.shown = PAGE; render(); } })));
    });
    if (state.q) {
      chips.appendChild(h('span', { class: 'chip' }, h('span', null, 'Поиск: ', h('b', { text: state.q })),
        h('button', { type: 'button', title: 'Очистить поиск', 'aria-label': 'Очистить поиск', icon: 'x', onclick: function () { searchInput.value = ''; state.q = ''; render(); } })));
    }
    if (chips.childNodes.length) {
      chips.appendChild(h('button', { type: 'button', class: 'link-btn', text: 'Сбросить к виду по умолчанию', onclick: function () { resetAll(); render(); } }));
    }
    popovers.forEach(function (p) {
      var n = p.f.values.filter(function (v) { return state.sel[p.f.key].has(v); }).length;
      p.btn.textContent = '';
      p.btn.classList.toggle('is-active', isFiltered(p.f));
      append(p.btn, [p.f.def.label + ' ']);
      if (isFiltered(p.f)) append(p.btn, h('span', { class: 'count', text: n }));
      p.btn.insertAdjacentHTML('beforeend', ICON.down);
      if (p.pop.classList.contains('open')) p.fill();
    });
  }

  function buildRow(it) {
    var id = String(it.id);
    var tr = h('tr', { class: 'row' + (S.isMuted && S.isMuted(it) ? ' is-muted' : ''), tabindex: '0', 'aria-expanded': state.open[id] ? 'true' : 'false', 'data-id': id });
    tr.appendChild(h('td', { class: 'col-chev', icon: 'chevron' }));
    S.renderCells(it, helpers).forEach(function (cell, i) {
      var c = S.columns[i];
      tr.appendChild(h('td', { class: c.className || null }, cell));
    });
    function toggle() {
      if (state.open[id]) { delete state.open[id]; tr.setAttribute('aria-expanded', 'false'); if (tr.nextSibling && tr.nextSibling.classList.contains('detail')) tr.nextSibling.remove(); }
      else { state.open[id] = true; tr.setAttribute('aria-expanded', 'true'); tr.after(buildDetail(it)); }
    }
    tr.addEventListener('click', function (e) { if (e.target.closest('a,button')) return; if (window.getSelection && String(window.getSelection())) return; toggle(); });
    tr.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
    return tr;
  }
  function buildDetail(it) {
    return h('tr', { class: 'detail' }, h('td', { colspan: S.columns.length + 1 }, S.renderDetail(it, helpers)));
  }

  var lastFiltered = [];
  function render(all) {
    var filtered = sorted(ITEMS.filter(function (it) { return matches(it); }));
    lastFiltered = filtered;
    renderChips();

    resultLine.textContent = '';
    append(resultLine, h('span', null, 'Показано ', h('b', { text: filtered.length }), ' из ' + ITEMS.length + ' ' + plural(ITEMS.length, S.noun[0], S.noun[1], S.noun[2])));
    if (S.hiddenNotice) {
      var notice = S.hiddenNotice(state, facetByKey, helpers, function () { state.shown = PAGE; render(); });
      if (notice) resultLine.appendChild(notice);
    }
    resultLine.appendChild(h('span', { class: 'spacer' }));
    if (Object.keys(state.open).length) {
      resultLine.appendChild(h('button', { type: 'button', class: 'link-btn no-print', text: 'Свернуть все', onclick: function () { state.open = {}; render(); } }));
    }

    tbody.textContent = '';
    var limit = all ? filtered.length : Math.min(state.shown, filtered.length);
    var frag = document.createDocumentFragment();
    for (var i = 0; i < limit; i++) {
      var it = filtered[i];
      frag.appendChild(buildRow(it));
      if (state.open[String(it.id)]) frag.appendChild(buildDetail(it));
    }
    tbody.appendChild(frag);
    table.style.display = filtered.length ? '' : 'none';

    emptyBox.textContent = '';
    if (!ITEMS.length) {
      emptyBox.appendChild(h('div', { class: 'empty' }, h('span', { icon: 'ok' }), h('h3', { text: S.emptyTitle }), h('div', { text: S.emptyText })));
    } else if (!filtered.length) {
      emptyBox.appendChild(h('div', { class: 'empty filtered' }, h('span', { icon: 'search' }), h('h3', { text: 'Нет находок, соответствующих фильтрам' }),
        h('button', { type: 'button', class: 'btn', text: 'Сбросить фильтры', onclick: function () { resetAll(); render(); } })));
    }

    more.textContent = '';
    if (limit < filtered.length) {
      var rest = filtered.length - limit;
      more.appendChild(h('button', { type: 'button', class: 'btn', text: 'Показать ещё ' + Math.min(PAGE, rest), onclick: function () { state.shown += PAGE; render(); } }));
      more.appendChild(h('button', { type: 'button', class: 'btn btn-ghost', text: 'Показать все (' + filtered.length + ')', onclick: function () { state.shown = filtered.length; render(); } }));
    }
  }

  function applyFacetValue(key, value, toggle) {
    var f = facetByKey[key];
    if (!f || f.values.indexOf(value) === -1) return;
    var sel = state.sel[key];
    if (toggle && sel.size === 1 && sel.has(value)) state.sel[key] = defaultSelection(f);
    else state.sel[key] = new Set([value]);
    state.shown = PAGE;
    render();
    var anchor = document.getElementById('findings-section');
    if (anchor) anchor.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  document.querySelectorAll('[data-filter]').forEach(function (el) {
    el.addEventListener('click', function () {
      var spec = el.getAttribute('data-filter');
      if (spec === '*') { resetAll(); render(); var a = document.getElementById('findings-section'); if (a) a.scrollIntoView({ behavior: 'smooth' }); return; }
      var idx = spec.indexOf(':');
      resetAll();
      applyFacetValue(spec.slice(0, idx), spec.slice(idx + 1), false);
    });
  });

  document.addEventListener('keydown', function (e) {
    var tag = (e.target && e.target.tagName) || '';
    if (e.key === '/' && tag !== 'INPUT' && tag !== 'TEXTAREA' && tag !== 'SELECT') { e.preventDefault(); searchInput.focus(); }
    if (e.key === 'Escape') closePopovers();
  });
  window.addEventListener('beforeprint', function () { render(true); });
  window.addEventListener('afterprint', function () { render(); });

  resetAll();
  render();
})();
"""


THEME_STORAGE_KEY = "secrets-scanner-report-theme"

# Runs in <head> before the stylesheet so the saved theme applies without a flash.
THEME_BOOT_JS = """(function(){try{var t=localStorage.getItem('%s');if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t);}catch(e){}})();""" % THEME_STORAGE_KEY

THEME_TOGGLE_JS = r"""
(function () {
  'use strict';
  var KEY = '%s';
  var root = document.documentElement;
  var btn = document.getElementById('theme-toggle');
  if (!btn) return;
  var mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  var SUN = '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="3" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M3.4 12.6l1.1-1.1M11.5 4.5l1.1-1.1" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';
  var MOON = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M13.5 9.6A5.5 5.5 0 0 1 6.4 2.5a5.5 5.5 0 1 0 7.1 7.1z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>';
  function current() {
    var t = root.getAttribute('data-theme');
    if (t === 'light' || t === 'dark') return t;
    return mq && mq.matches ? 'dark' : 'light';
  }
  function paint() {
    var dark = current() === 'dark';
    var label = dark ? 'Включить светлую тему' : 'Включить тёмную тему';
    btn.innerHTML = dark ? SUN : MOON;
    btn.setAttribute('title', label);
    btn.setAttribute('aria-label', label);
  }
  btn.addEventListener('click', function () {
    var next = current() === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem(KEY, next); } catch (e) { /* storage unavailable: theme still switches for this view */ }
    paint();
  });
  if (mq) {
    var onChange = function () { if (!root.getAttribute('data-theme')) paint(); };
    if (mq.addEventListener) mq.addEventListener('change', onChange); else if (mq.addListener) mq.addListener(onChange);
  }
  // Always print in the light theme.
  var saved = null;
  window.addEventListener('beforeprint', function () { saved = root.getAttribute('data-theme'); root.setAttribute('data-theme', 'light'); });
  window.addEventListener('afterprint', function () { if (saved) root.setAttribute('data-theme', saved); else root.removeAttribute('data-theme'); });
  paint();
})();
""" % THEME_STORAGE_KEY


BRAND_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.5 3 3.5v4c0 3.2 2.1 5.9 5 7 2.9-1.1 5-3.8 5-7v-4l-5-2z" fill="currentColor"/></svg>'
WARN_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2 1.5 13.5h13L8 2z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M8 6.5v3.2M8 11.6v.2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>'


def render_page(*, title: str, kind_label: str, overview_html: str, kpis_html: str,
                findings_title: str, findings_sub: str, data: dict, schema_js: str) -> str:
    generated = esc(datetime.now().strftime("%d.%m.%Y %H:%M"))
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;">
<meta name="robots" content="noindex">
<title>{esc(title)}</title>
<script>{THEME_BOOT_JS}</script>
<style>{REPORT_CSS}</style>
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <div class="brand"><span class="brand-mark">{BRAND_ICON}</span>Secrets Scanner <span class="brand-sub">· {esc(kind_label)}</span></div>
    <span class="topbar-spacer"></span>
    <button type="button" class="btn btn-sm btn-icon no-print" id="theme-toggle"></button>
    <button type="button" class="btn btn-sm no-print" onclick="window.print()">Печать / PDF</button>
  </div>
</header>
<main class="page">
  <section id="summary" class="overview" aria-label="Сводка">
    {overview_html}
  </section>
  <div class="kpis" aria-label="Ключевые показатели">{kpis_html}</div>
  <section id="findings-section" class="section" aria-labelledby="findings-h">
    <div class="section-head"><h2 id="findings-h">{esc(findings_title)}</h2><span class="sub">{esc(findings_sub)}</span></div>
    <div id="findings" class="card findings">
      <noscript><div class="empty">Для просмотра списка находок включите JavaScript.</div></noscript>
    </div>
  </section>
</main>
<footer class="footer">
  <span>Отчёт сформирован Secrets Scanner · {generated}</span>
  <span class="warn">{WARN_ICON} Отчёт может содержать конфиденциальную информацию. Не передавайте его за пределы команды.</span>
</footer>
<script type="application/json" id="report-data">{embed_json(data)}</script>
<script>{schema_js}</script>
<script>{THEME_TOGGLE_JS}</script>
<script>{REPORT_CORE_JS}</script>
</body>
</html>
"""
