import html
import urllib.parse
import re
from datetime import datetime

from utils.report_ui import (
    esc,
    format_dt,
    format_duration,
    display_path,
    split_path,
    mask_secret,
    safe_href,
    meta_item,
    kpi,
    verdict_block,
    render_page,
    copy_value_html,
)

def sanitize_input(text):
    """Дополнительная санитизация входных данных"""
    if not text:
        return ""

    # Базовое экранирование HTML
    text = html.escape(str(text), quote=True)

    # Удаление потенциально опасных символов для JavaScript
    dangerous_chars = ['<', '>', '"', "'", '&', '\n', '\r', '\t']
    for char in dangerous_chars:
        if char in text:
            text = text.replace(char, html.escape(char))

    return text

def sanitize_url(url):
    """Безопасная санитизация URL"""
    if not url:
        return ""

    # Проверяем, что URL начинается с разрешенных протоколов
    allowed_protocols = ['http://', 'https://']
    url_lower = url.lower().strip()

    if not any(url_lower.startswith(protocol) for protocol in allowed_protocols):
        return "#"  # Возвращаем безопасную заглушку

    # Удаляем потенциально опасные символы
    dangerous_patterns = [
        r'javascript:',
        r'data:',
        r'vbscript:',
        r'on\w+\s*=',  # onclick, onload и т.д.
        r'<script',
        r'</script>',
    ]

    for pattern in dangerous_patterns:
        url = re.sub(pattern, '', url, flags=re.IGNORECASE)

    # URL encode для дополнительной безопасности
    return urllib.parse.quote(url, safe=':/?#[]@!$&\'()*+,;=')

def sanitize_js_string(text):
    """Безопасная подготовка строки для использования в JavaScript"""
    if not text:
        return ""

    # Экранируем специальные символы для JavaScript
    text = str(text)
    text = text.replace('\\', '\\\\')  # Обратные слеши
    text = text.replace('"', '\\"')    # Двойные кавычки
    text = text.replace("'", "\\'")    # Одинарные кавычки
    text = text.replace('\n', '\\n')   # Переносы строк
    text = text.replace('\r', '\\r')   # Возврат каретки
    text = text.replace('\t', '\\t')   # Табуляция
    text = text.replace('</', '<\\/')  # Закрывающие теги

    return text

def normalize_report_status(status):
    if not status or status == "null":
        return "No status"
    return str(status)


def format_status_badge(status):
    normalized = normalize_report_status(status)
    safe_status = sanitize_input(normalized)
    if normalized == "Confirmed":
        css_class = "status-confirmed"
    elif normalized == "Refuted":
        css_class = "status-refuted"
    else:
        css_class = "status-none"
        safe_status = "Без статуса"
    return f'<span class="status-badge {css_class}">{safe_status}</span>'


# ---------------------------------------------------------------------------
# Secrets report
# ---------------------------------------------------------------------------

def build_secret_file_url(repo_url, repo_commit, hub_type, path, line, secret_value):
    """Link to the finding in the repository UI (same URL formats as before)."""
    repo_url = (repo_url or "").strip()
    repo_commit = repo_commit or "Unknown"
    path = path or ""
    hub_type = hub_type or ""
    try:
        if "devzone.local" in repo_url:
            # DevZone/GitLab URL format
            url = (
                f"{repo_url}/-/blob/{repo_commit}/{urllib.parse.quote(path)}#L{line}-{line}"
            ).replace("/devzone_repository/", "")
        elif hub_type.lower() == "azure":
            # Azure DevOps URL format
            end_column = len(secret_value or "") + 1
            url = (
                f"{repo_url}?path={urllib.parse.quote(path)}&version=GC{repo_commit}"
                f"&line={line}&lineEnd={line}&lineStartColumn=1&lineEndColumn={end_column}&_a=contents"
            )
        else:
            # Default/GitHub URL format
            url = f"{repo_url}/blob/{repo_commit}{urllib.parse.quote(path)}?plain=1#L{line}"
    except Exception as error:
        print(f"Error building file URL: {error}")
        return ""
    return safe_href(url)


def _refuted_in(origin, current_scan_id):
    """Serialize where the refutation was made: {'commit', 'date', 'current'} or None."""
    if not origin:
        return None
    commit = origin.get("commit") or ""
    scan_id = origin.get("scan_id") or ""
    if not commit and not scan_id:
        return None
    return {
        "commit": commit,
        "date": format_dt(origin.get("date")),
        "current": bool(scan_id and scan_id == current_scan_id),
    }


def _secret_item(secret, repo_url, repo_commit, hub_type, origin=None, current_scan_id=None):
    raw_path = secret.path or ""
    path = display_path(raw_path)
    directory, filename, component, extension = split_path(path)
    line = int(secret.line) if str(secret.line).isdigit() else 1
    secret_value = secret.secret or ""
    status = normalize_report_status(secret.status)
    is_refuted = status == "Refuted"
    return {
        "id": secret.id,
        "sev": secret.severity or "Unknown",
        "type": secret.type or "Unknown",
        "status": status,
        "path": path or "(не указан)",
        "dir": directory,
        "file": filename or path or "(не указан)",
        "component": component,
        "ext": extension,
        "line": line,
        "masked": mask_secret(secret_value),
        "url": build_secret_file_url(repo_url, repo_commit, hub_type, raw_path, line, secret_value),
        "hash": secret.hash_from_ci or "",
        "refutedAt": format_dt(secret.refuted_at) if is_refuted else "",
        "refutedSort": secret.refuted_at.isoformat() if is_refuted and secret.refuted_at else "",
        "refutedIn": _refuted_in(origin, current_scan_id) if is_refuted else None,
        "confirmedBy": (secret.confirmed_by or "") if status == "Confirmed" else "",
    }


def compute_secrets_verdict(items):
    """Итоговый статус отчёта по секретам.

    Учитываются только активные (не опровергнутые) находки:
      * есть High или подтверждённые секреты -> «Не пройдено»;
      * остались только Potential без статуса  -> «Требует проверки»;
      * активных находок нет                    -> «Пройдено».
    """
    active = [i for i in items if i["status"] != "Refuted"]
    high = sum(1 for i in active if i["sev"] == "High")
    confirmed = sum(1 for i in active if i["status"] == "Confirmed")
    if high or confirmed:
        parts = []
        if high:
            parts.append(f"{high} уровня High")
        if confirmed:
            parts.append(f"{confirmed} подтверждённых")
        return ("danger", "Не пройдено",
                f"Обнаружены активные секреты: {', '.join(parts)}. Требуются ротация и удаление из репозитория.")
    if active:
        return ("warning", "Требует проверки",
                f"{len(active)} потенциальных секретов ожидают разбора аналитиком.")
    return ("success", "Пройдено", "Активных секретов не обнаружено.")


_SECRETS_SCHEMA_JS = r"""
window.ReportSchema = (function () {
  var SEV_ORDER = ['High', 'Potential', 'Unknown'];
  var SEV_CLASS = { High: 'sev-crit', Potential: 'sev-med' };
  var ST_ORDER = ['Confirmed', 'No status', 'Refuted'];
  var ST_LABEL = { 'Confirmed': 'Подтверждён', 'No status': 'Без статуса', 'Refuted': 'Опровергнут' };
  var ST_CLASS = { 'Confirmed': 'st-confirmed', 'No status': 'st-open', 'Refuted': 'st-refuted' };
  function rank(order, v) { var i = order.indexOf(v); return i === -1 ? order.length : i; }
  function bySev(a, b) { return rank(SEV_ORDER, a.sev) - rank(SEV_ORDER, b.sev) || rank(ST_ORDER, a.status) - rank(ST_ORDER, b.status); }
  function byPath(a, b) { return a.path.localeCompare(b.path) || a.line - b.line; }

  function sevBadge(h, v) { return h('span', { class: 'sev ' + (SEV_CLASS[v] || 'sev-none'), text: v }); }
  function statusBadge(h, it) {
    var wrap = h('span', null, h('span', { class: 'st ' + (ST_CLASS[it.status] || 'st-open'), text: ST_LABEL[it.status] || it.status }));
    if (it.status === 'Refuted' && it.refutedAt) wrap.appendChild(h('span', { class: 'st-date', text: it.refutedAt }));
    return wrap;
  }
  function refutedInText(r) {
    if (!r) return '';
    if (r.current) return 'в этом сканировании';
    var parts = [];
    if (r.commit) parts.push('коммит ' + r.commit.slice(0, 12));
    if (r.date) parts.push('от ' + r.date);
    return parts.join(' ');
  }
  function kv(h, rows) {
    var dl = h('dl', { class: 'kv kv-2' });
    rows.forEach(function (r) { if (r && r[1] !== '' && r[1] !== null && r[1] !== undefined) { dl.appendChild(h('dt', { text: r[0] })); dl.appendChild(h('dd', null, r[1])); } });
    return dl;
  }

  return {
    noun: ['находки', 'находок', 'находок'],
    searchPlaceholder: 'Поиск по значению, пути, файлу, типу, ID…',
    emptyTitle: 'Секреты не обнаружены',
    emptyText: 'Сканирование не выявило потенциальных утечек секретов.',
    facets: [
      { key: 'sev', label: 'Критичность', get: function (i) { return i.sev; }, order: SEV_ORDER },
      { key: 'status', label: 'Статус', get: function (i) { return i.status; }, order: ST_ORDER, labels: ST_LABEL, hiddenByDefault: ['Refuted'] },
      { key: 'type', label: 'Тип секрета', get: function (i) { return i.type; } },
      { key: 'component', label: 'Компонент', get: function (i) { return i.component; } },
      { key: 'path', label: 'Файл', get: function (i) { return i.path; } },
      { key: 'ext', label: 'Тип файла', get: function (i) { return i.ext; } }
    ],
    searchText: function (i) { return [i.masked, i.path, i.type, i.hash, i.component, i.confirmedBy, i.refutedIn ? i.refutedIn.commit : ''].join(' '); },
    sorts: [
      { key: 'sev', label: 'Сначала критичные', cmp: function (a, b) { return bySev(a, b) || byPath(a, b); } },
      { key: 'path', label: 'По пути к файлу', cmp: byPath },
      { key: 'type', label: 'По типу секрета', cmp: function (a, b) { return a.type.localeCompare(b.type) || bySev(a, b) || byPath(a, b); } },
      { key: 'refuted', label: 'Недавно опровергнутые', cmp: function (a, b) { return (b.refutedSort || '').localeCompare(a.refutedSort || '') || bySev(a, b) || byPath(a, b); } }
    ],
    columns: [
      { label: 'Критичность' },
      { label: 'Тип' },
      { label: 'Расположение' },
      { label: 'Значение', className: 'col-hide-sm' },
      { label: 'Статус' }
    ],
    isMuted: function (i) { return i.status === 'Refuted'; },
    renderCells: function (i, H) {
      var h = H.h;
      return [
        sevBadge(h, i.sev),
        h('span', { class: 'type-name', text: i.type }),
        h('div', null,
          h('div', null, h('span', { class: 'loc-file', text: i.file }), ' ', h('span', { class: 'loc-line', text: ':' + i.line })),
          i.dir ? h('div', { class: 'loc-dir', text: i.dir + '/' }) : null),
        h('span', { class: 'secret-mask', text: i.masked }),
        statusBadge(h, i)
      ];
    },
    renderDetail: function (i, H) {
      var h = H.h;
      var box = h('div', { class: 'detail-box' }, h('h4', { text: 'Сведения о находке' }));
      if (i.status === 'Refuted') {
        var where = refutedInText(i.refutedIn);
        box.appendChild(h('div', { class: 'callout' }, h('b', { text: 'Опровергнут' }),
          i.refutedAt ? ' ' + i.refutedAt : '', where ? ' · ' + where : ''));
      }
      box.appendChild(kv(h, [
        ['Критичность', sevBadge(h, i.sev)],
        ['Статус', statusBadge(h, i)],
        ['Тип', i.type],
        ['Значение', h('span', { class: 'secret-mask', text: i.masked })],
        ['Файл', h('span', { class: 'mono', text: i.path })],
        ['Строка', String(i.line)],
        ['Компонент', i.component],
        ['Подтвердил', i.confirmedBy],
        ['Опровергнут в', i.refutedIn ? (i.refutedIn.current ? 'этом сканировании' : h('div', null,
            i.refutedIn.commit ? H.copyValue(i.refutedIn.commit, 'Копировать коммит', i.refutedIn.commit.slice(0, 12)) : null,
            i.refutedIn.date ? h('div', { class: 'sub-text', text: 'сканирование от ' + i.refutedIn.date }) : null)) : ''],
        ['ID находки', i.hash ? H.copyValue(i.hash, 'Копировать ID') : '']
      ]));
      var actions = h('div', { class: 'detail-actions' });
      if (i.url) actions.appendChild(h('a', { class: 'btn btn-sm', href: i.url, target: '_blank', rel: 'noopener noreferrer', icon: 'ext' }, 'Открыть в репозитории'));
      var cp = h('button', { type: 'button', class: 'btn btn-sm', icon: 'copy' }, 'Копировать путь');
      cp.addEventListener('click', function (e) { e.stopPropagation(); H.copyText(i.path + ':' + i.line, cp); });
      actions.appendChild(cp);
      box.appendChild(actions);
      return box;
    },
    hiddenNotice: function (state, facets, H, rerender) {
      var f = facets.status;
      if (!f || !f.total.Refuted || state.sel.status.has('Refuted')) return null;
      var h = H.h;
      return h('span', { class: 'notice no-print' }, 'Опровергнутые (' + f.total.Refuted + ') скрыты.',
        h('button', { type: 'button', class: 'link-btn', text: 'Показать', onclick: function () { state.sel.status.add('Refuted'); rerender(); } }));
    }
  };
})();
"""


def generate_html_report(scan, project, secrets, HubType, refuted_secrets=None, refuted_total=None,
                         refutation_origins=None):
    """Build the HTML report for a secrets scan.

    `secrets` is exactly what the export endpoint selected (unchanged contract).
    `refuted_secrets` are the scan's refuted findings, always appended to the report;
    they are hidden by default there and can be shown through the status filter.
    `refutation_origins` maps secret id -> {'scan_id', 'commit', 'date'} of the scan
    where the finding was refuted (only for secrets where this is known).
    """
    repo_url_raw = (project.repo_url or "").strip()
    repo_commit_raw = scan.repo_commit or "Unknown"
    hub_type = HubType or ""
    origins = refutation_origins or {}

    items = []
    seen = set()
    for secret in list(secrets or []) + list(refuted_secrets or []):
        if secret.id in seen:
            continue
        seen.add(secret.id)
        items.append(_secret_item(
            secret, repo_url_raw, repo_commit_raw, hub_type, origins.get(secret.id), scan.id
        ))

    active = [i for i in items if i["status"] != "Refuted"]
    high = sum(1 for i in active if i["sev"] == "High")
    potential = sum(1 for i in active if i["sev"] == "Potential")
    confirmed = sum(1 for i in active if i["status"] == "Confirmed")
    open_count = sum(1 for i in active if i["status"] == "No status")
    refuted = len(items) - len(active)
    tone, verdict_title, verdict_text = compute_secrets_verdict(items)

    # ---- overview ----
    repo_href = safe_href(repo_url_raw)
    repo_html = (
        f'<a href="{esc(repo_href)}" target="_blank" rel="noopener noreferrer">{esc(repo_url_raw)}</a>'
        if repo_href else esc(repo_url_raw or "—")
    )
    ref_html = ""
    if scan.ref:
        ref_label = {"branch": "ветка", "tag": "тег", "commit": "коммит"}.get((scan.ref_type or "").lower(), scan.ref_type or "")
        ref_html = esc(scan.ref) + (f' <span class="sub-text">({esc(ref_label)})</span>' if ref_label else "")
    commit_html = ""
    if scan.repo_commit:
        commit_html = copy_value_html(scan.repo_commit, "Копировать коммит", scan.repo_commit[:12])
    files_html = ""
    if scan.files_scanned is not None:
        files_html = esc(f"{scan.files_scanned:,}".replace(",", " "))
        if scan.excluded_files_count:
            files_html += f' <span class="sub-text">· исключено {esc(scan.excluded_files_count)}</span>'

    meta_html = "".join([
        meta_item("Ветка / тег", ref_html),
        meta_item("Коммит", commit_html, mono=True),
        meta_item("Дата сканирования", esc(format_dt(scan.completed_at) or "—")),
        meta_item("Длительность", esc(format_duration(scan.started_at, scan.completed_at))),
        meta_item("Файлов просканировано", files_html),
        meta_item("ID сканирования", copy_value_html(scan.id, "Копировать ID"), mono=True),
    ])

    total_all = len(items)
    reviewed = confirmed + refuted
    pct = round(reviewed / total_all * 100) if total_all else 100

    def seg(n, color, label):
        if not n:
            return ""
        return f'<span style="width:{n / total_all * 100:.3f}%;background:{color}" title="{esc(label)}: {n}"></span>'

    triage_html = ""
    if total_all:
        triage_html = (
            '<div class="card triage">'
            f'<div class="triage-head"><b>Разбор находок</b>'
            f'<span class="sub-text">{reviewed} из {total_all} · {pct}%</span></div>'
            '<div class="progress-bar" style="margin-top:8px">'
            + seg(confirmed, "var(--crit)", "Подтверждено")
            + seg(refuted, "var(--ok)", "Опровергнуто")
            + seg(open_count, "var(--border-strong)", "Без статуса")
            + '</div><div class="progress-legend">'
            f'<span><i class="dot" style="background:var(--crit)"></i>Подтверждено {confirmed}</span>'
            f'<span><i class="dot" style="background:var(--ok)"></i>Опровергнуто {refuted}</span>'
            f'<span><i class="dot" style="background:var(--border-strong)"></i>Без статуса {open_count}</span>'
            '</div></div>'
        )

    overview_html = (
        '<div class="card scan-card">'
        '<div class="eyebrow">Отчёт о сканировании секретов</div>'
        f'<h1 class="scan-title">{esc(project.name)}</h1>'
        f'<div class="scan-repo">{repo_html}</div>'
        f'<dl class="meta">{meta_html}</dl>'
        '</div>'
        f'<div class="overview-side">{verdict_block(tone, verdict_title, verdict_text)}{triage_html}</div>'
    )

    refuted_hint = "скрыты по умолчанию"
    if refuted_total is not None and refuted_total > refuted:
        refuted_hint = f"в отчёте {refuted} из {refuted_total}"
    kpis_html = "".join([
        kpi("Активные находки", len(active), "без учёта опровергнутых", "", "*"),
        kpi("High", high, "высокая критичность", "crit" if high else "", "sev:High"),
        kpi("Potential", potential, "требуют проверки", "med" if potential else "", "sev:Potential"),
        kpi("Подтверждено", confirmed, "реальные секреты", "high" if confirmed else "", "status:Confirmed"),
        kpi("Без статуса", open_count, "ожидают разбора", "", "status:No status"),
        kpi("Опровергнуто", refuted, refuted_hint, "muted", "status:Refuted"),
    ])

    return render_page(
        title=f"{project.name} — отчёт Secrets Scanner",
        kind_label="Отчёт о секретах",
        overview_html=overview_html,
        kpis_html=kpis_html,
        findings_title="Находки",
        findings_sub="Нажмите на строку, чтобы увидеть детали",
        data={"items": items},
        schema_js=_SECRETS_SCHEMA_JS,
    )


def attachment_content_disposition(filename: str) -> str:
    """Content-Disposition header for file downloads (supports non-ASCII filenames)."""
    ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "export"
    quoted_name = urllib.parse.quote(filename)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted_name}"
