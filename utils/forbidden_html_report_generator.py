import json
import re
import urllib.parse
from datetime import datetime

from utils.html_report_generator import sanitize_input, sanitize_js_string, sanitize_url  # noqa: F401 (re-exported)
from utils.report_ui import (
    esc,
    format_dt,
    format_duration,
    display_path,
    split_path,
    safe_href,
    meta_item,
    kpi,
    verdict_block,
    render_page,
    copy_value_html,
)


def _parse_violation_reasons(raw_value) -> list:
    if not raw_value:
        return []
    if isinstance(raw_value, list):
        return [str(item) for item in raw_value]
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    return [str(raw_value)]


def _format_file_size(size) -> str:
    if size is None:
        return "—"
    try:
        value = int(size)
    except (TypeError, ValueError):
        return "—"
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value / (1024 * 1024):.1f} MB"


def _build_file_url(project_repo_url: str, repo_commit: str, hub_type: str, path: str) -> str:
    try:
        if "devzone.local" in (project_repo_url or ""):
            return f"{project_repo_url}/-/blob/{repo_commit}/{urllib.parse.quote(path or '')}"
        if (hub_type or "").lower() == "azure":
            return (
                f"{project_repo_url}?path={urllib.parse.quote(path or '')}"
                f"&version=GC{repo_commit}&_a=contents"
            )
        safe_path = "/".join(urllib.parse.quote(part) for part in (path or "").replace("\\", "/").split("/"))
        return f"{project_repo_url}/blob/{repo_commit}{safe_path}?plain=1"
    except Exception:
        return "#"


def _status_value(status) -> str:
    if not status or status == "null":
        return "No status"
    return str(status)


def resolve_forbidden_report_passed(scan, violations) -> bool:
    """Итоговый статус: решение сканера (scan.forbidden_passed), иначе — отсутствие blocking-нарушений."""
    if scan.forbidden_passed is not None:
        return bool(scan.forbidden_passed)
    return not any(v.is_blocking for v in violations)


_FORBIDDEN_SCHEMA_JS = r"""
window.ReportSchema = (function () {
  var LEVEL_ORDER = ['Blocking', 'Non-blocking'];
  var LEVEL_CLASS = { 'Blocking': 'sev-crit', 'Non-blocking': 'sev-none' };
  var ST_ORDER = ['Confirmed', 'No status', 'Refuted'];
  var ST_LABEL = { 'Confirmed': 'Подтверждено', 'No status': 'Без статуса', 'Refuted': 'Опровергнуто' };
  var ST_CLASS = { 'Confirmed': 'st-confirmed', 'No status': 'st-open', 'Refuted': 'st-refuted' };
  function rank(order, v) { var i = order.indexOf(v); return i === -1 ? order.length : i; }
  function byPath(a, b) { return a.path.localeCompare(b.path); }
  function byLevel(a, b) { return rank(LEVEL_ORDER, a.level) - rank(LEVEL_ORDER, b.level); }
  function levelBadge(h, v) { return h('span', { class: 'sev ' + (LEVEL_CLASS[v] || 'sev-none'), text: v }); }
  function statusBadge(h, it) {
    var wrap = h('span', null, h('span', { class: 'st ' + (ST_CLASS[it.status] || 'st-open'), text: ST_LABEL[it.status] || it.status }));
    if (it.status === 'Refuted' && it.refutedAt) wrap.appendChild(h('span', { class: 'st-date', text: it.refutedAt }));
    return wrap;
  }
  function kv(h, rows) {
    var dl = h('dl', { class: 'kv' });
    rows.forEach(function (r) { if (r && r[1] !== '' && r[1] !== null && r[1] !== undefined) { dl.appendChild(h('dt', { text: r[0] })); dl.appendChild(h('dd', null, r[1])); } });
    return dl;
  }

  return {
    noun: ['нарушения', 'нарушений', 'нарушений'],
    searchPlaceholder: 'Поиск по пути, категории, причине…',
    emptyTitle: 'Нарушения не обнаружены',
    emptyText: 'Сканирование не выявило запрещённых файлов.',
    facets: [
      { key: 'level', label: 'Уровень', get: function (i) { return i.level; }, order: LEVEL_ORDER },
      { key: 'status', label: 'Статус', get: function (i) { return i.status; }, order: ST_ORDER, labels: ST_LABEL, hiddenByDefault: ['Refuted'] },
      { key: 'category', label: 'Категория', get: function (i) { return i.category; } },
      { key: 'component', label: 'Компонент', get: function (i) { return i.component; } },
      { key: 'lang', label: 'Язык', get: function (i) { return i.lang; } },
      { key: 'ext', label: 'Расширение', get: function (i) { return i.ext; } }
    ],
    searchText: function (i) { return [i.path, i.category, i.lang, i.ext, i.reasons.join(' '), i.binaryReason, i.hash].join(' '); },
    sorts: [
      { key: 'level', label: 'Сначала blocking', cmp: function (a, b) { return byLevel(a, b) || a.category.localeCompare(b.category) || byPath(a, b); } },
      { key: 'path', label: 'По пути к файлу', cmp: byPath },
      { key: 'category', label: 'По категории', cmp: function (a, b) { return a.category.localeCompare(b.category) || byLevel(a, b) || byPath(a, b); } },
      { key: 'size', label: 'По размеру', cmp: function (a, b) { return (b.size || 0) - (a.size || 0) || byPath(a, b); } }
    ],
    columns: [
      { label: 'Уровень' },
      { label: 'Файл' },
      { label: 'Категория' },
      { label: 'Размер', className: 'col-hide-sm' },
      { label: 'Статус' }
    ],
    isMuted: function (i) { return i.status === 'Refuted'; },
    renderCells: function (i, H) {
      var h = H.h;
      return [
        levelBadge(h, i.level),
        h('div', null, h('div', { class: 'loc-file', text: i.file }), i.dir ? h('div', { class: 'loc-dir', text: i.dir + '/' }) : null),
        h('div', null, h('div', { text: i.category }), h('div', { class: 'sub-text', text: [i.lang, i.ext].filter(Boolean).join(' · ') })),
        h('span', { class: 'sub-text', text: i.sizeText }),
        statusBadge(h, i)
      ];
    },
    renderDetail: function (i, H) {
      var h = H.h;
      var reasonsBox = h('div', { class: 'detail-box' }, h('h4', { text: 'Причины нарушения' }));
      if (i.reasons.length) {
        var ul = h('ul', { class: 'reasons' });
        i.reasons.forEach(function (r) { ul.appendChild(h('li', { text: r })); });
        reasonsBox.appendChild(ul);
      } else reasonsBox.appendChild(h('div', { class: 'code-empty', text: 'Причины не указаны.' }));
      var actions = h('div', { class: 'detail-actions' });
      if (i.url) actions.appendChild(h('a', { class: 'btn btn-sm', href: i.url, target: '_blank', rel: 'noopener noreferrer', icon: 'ext' }, 'Открыть в репозитории'));
      actions.appendChild(h('span', null, 'Путь', H.copyBtn(i.path, 'Копировать путь')));
      reasonsBox.appendChild(actions);
      var info = h('div', { class: 'detail-box' }, h('h4', { text: 'Сведения' }));
      info.appendChild(kv(h, [
        ['Уровень', levelBadge(h, i.level)],
        ['Статус', statusBadge(h, i)],
        ['Подтвердил', i.confirmedBy],
        ['Категория', i.category],
        ['Компонент', i.component],
        ['Файл', h('span', { class: 'mono', text: i.path })],
        ['Язык', i.lang],
        ['Расширение', i.ext],
        ['Размер', i.sizeText],
        ['Бинарный', i.binary ? ('да' + (i.binaryReason ? ' — ' + i.binaryReason : '')) : ''],
        ['ID находки', i.hash ? H.copyValue(i.hash, 'Копировать ID') : '']
      ]));
      return h('div', { class: 'detail-grid' }, reasonsBox, info);
    },
    hiddenNotice: function (state, facets, H, rerender) {
      var f = facets.status;
      if (!f || !f.total.Refuted || state.sel.status.has('Refuted')) return null;
      return H.h('span', { class: 'notice no-print' }, 'Опровергнутые (' + f.total.Refuted + ') скрыты.',
        H.h('button', { type: 'button', class: 'link-btn', text: 'Показать', onclick: function () { state.sel.status.add('Refuted'); rerender(); } }));
    }
  };
})();
"""


def generate_forbidden_html_report(scan, project, violations, hub_type):
    repo_url_raw = (project.repo_url or "").strip()
    violations = list(violations or [])

    items = []
    for v in violations:
        path = display_path(v.path or "")
        directory, filename, component, guessed_ext = split_path(path)
        status = _status_value(v.status)
        items.append({
            "id": v.id,
            "level": "Blocking" if v.is_blocking else "Non-blocking",
            "status": status,
            "path": path or "(не указан)",
            "dir": directory,
            "file": filename or path or "(не указан)",
            "component": component,
            "category": v.category or "other",
            "lang": v.language or "—",
            "ext": v.extension or guessed_ext,
            "size": v.size if isinstance(v.size, int) else None,
            "sizeText": _format_file_size(v.size),
            "binary": bool(v.is_binary),
            "binaryReason": v.binary_reason or "",
            "reasons": _parse_violation_reasons(v.violation_reasons),
            "hash": v.hash_from_ci or "",
            "url": safe_href(_build_file_url(repo_url_raw, scan.repo_commit or "", hub_type, v.path or "")),
            "refutedAt": format_dt(v.refuted_at) if status == "Refuted" else "",
            "confirmedBy": (v.confirmed_by or "") if status == "Confirmed" else "",
        })

    active = [i for i in items if i["status"] != "Refuted"]
    blocking = sum(1 for i in active if i["level"] == "Blocking")
    non_blocking = len(active) - blocking
    binary = sum(1 for i in active if i["binary"])
    categories = len({i["category"] for i in active})

    passed = resolve_forbidden_report_passed(scan, violations)
    if passed:
        tone, title = "success", "Пройдено"
        text = ("Блокирующих нарушений нет." if not active
                else f"Блокирующих нарушений нет; {len(active)} неблокирующих нарушений для сведения.")
    else:
        tone, title = "danger", "Не пройдено"
        text = (f"Обнаружено блокирующих нарушений: {blocking}. Удалите запрещённые файлы из репозитория."
                if blocking else "Проверка не пройдена по решению сканера.")

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

    meta_html = "".join([
        meta_item("Ветка / тег", ref_html),
        meta_item("Коммит", commit_html, mono=True),
        meta_item("Дата сканирования", esc(format_dt(scan.completed_at) or "—")),
        meta_item("Длительность", esc(format_duration(scan.started_at, scan.completed_at))),
        meta_item("Файлов просканировано", files_html),
        meta_item("ID сканирования", copy_value_html(scan.id, "Копировать ID"), mono=True),
    ])

    overview_html = (
        '<div class="card scan-card">'
        '<div class="eyebrow">Отчёт о проверке запрещённых файлов</div>'
        f'<h1 class="scan-title">{esc(project.name)}</h1>'
        f'<div class="scan-repo">{repo_html}</div>'
        f'<dl class="meta">{meta_html}</dl>'
        '</div>'
        f'<div class="overview-side">{verdict_block(tone, title, text)}</div>'
    )

    kpis_html = "".join([
        kpi("Нарушения", len(active), "всего в отчёте", "", "*"),
        kpi("Blocking", blocking, "блокируют проверку", "crit" if blocking else "", "level:Blocking"),
        kpi("Non-blocking", non_blocking, "для сведения", "", "level:Non-blocking"),
        kpi("Бинарные файлы", binary, "среди нарушений", "", ""),
        kpi("Категорий", categories, "типов нарушений", "", ""),
    ])

    return render_page(
        title=f"{project.name} — отчёт Forbidden Check",
        kind_label="Запрещённые файлы",
        overview_html=overview_html,
        kpis_html=kpis_html,
        findings_title="Нарушения",
        findings_sub="Нажмите на строку, чтобы увидеть причины и детали",
        data={"items": items},
        schema_js=_FORBIDDEN_SCHEMA_JS,
    )
