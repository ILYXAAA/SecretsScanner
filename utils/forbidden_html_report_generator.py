import json
import re
import urllib.parse
from datetime import datetime

from utils.html_report_generator import sanitize_input, sanitize_js_string, sanitize_url


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


def generate_forbidden_html_report(scan, project, violations, hub_type):
    project_name = sanitize_input(project.name)
    project_repo_url = sanitize_url(project.repo_url)
    repo_commit = sanitize_input(scan.repo_commit or "Unknown")
    hub_type_safe = sanitize_input(hub_type)

    total_violations = len(violations)
    scan_date = sanitize_input(
        scan.completed_at.strftime("%d.%m.%Y %H:%M") if scan.completed_at else "Unknown"
    )
    files_scanned = sanitize_input(scan.files_scanned or "Unknown")
    blocking_count = sum(1 for v in violations if v.is_blocking)

    violations_by_category = {}
    for violation in violations:
        category = sanitize_input(violation.category or "other")
        violations_by_category.setdefault(category, []).append(violation)

    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';">
    <title>Отчет {project_name} Forbidden Check</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f8f9fa;
            padding: 2rem;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #7c3aed 0%, #5b21b6 100%);
            color: white;
            padding: 2rem;
            text-align: center;
        }}
        .header h1 {{ font-size: 2.5rem; margin-bottom: 0.5rem; font-weight: 700; }}
        .header p {{ font-size: 1.1rem; opacity: 0.9; }}
        .meta-info {{ background: #f8f9fa; padding: 1.5rem 2rem; border-bottom: 1px solid #e9ecef; }}
        .meta-item {{ display: flex; margin-bottom: 0.75rem; }}
        .meta-item:last-child {{ margin-bottom: 0; }}
        .meta-label {{ font-weight: 600; color: #6c757d; min-width: 180px; flex-shrink: 0; }}
        .meta-value {{
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            background: #e9ecef;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.9rem;
            word-break: break-all;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 0.75rem;
            margin-top: 1.5rem;
        }}
        .stat-card {{
            background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 1rem;
            text-align: center;
        }}
        .stat-number {{ font-size: 1.5rem; font-weight: 600; color: #495057; margin-bottom: 0.5rem; }}
        .stat-label {{
            font-size: 0.9rem;
            color: #6c757d;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .violations-section {{ padding: 2rem; }}
        .type-group {{ margin-bottom: 2rem; }}
        .type-header {{
            background: #f8f9fa;
            padding: 1rem 1.5rem;
            border-left: 4px solid #7c3aed;
            border-radius: 0 8px 8px 0;
            cursor: pointer;
            user-select: none;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .type-header:hover {{ background: #ede9fe; }}
        .type-title {{ font-size: 1.3rem; font-weight: 600; margin-bottom: 0.25rem; }}
        .type-count {{ color: #6c757d; font-size: 0.9rem; }}
        .collapse-indicator {{ font-size: 1.2rem; color: #6c757d; }}
        .type-content {{ overflow: hidden; transition: max-height 0.3s ease; }}
        .type-content.collapsed {{ max-height: 0; }}
        .type-content.expanded {{ max-height: none; }}
        .violations-table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin-top: 1rem;
        }}
        .violations-table th {{
            background: #5b21b6;
            color: white;
            padding: 1rem;
            text-align: left;
            font-weight: 600;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .violations-table td {{
            padding: 1rem;
            border-bottom: 1px solid #e9ecef;
            vertical-align: top;
        }}
        .violations-table tr:hover {{ background: #f8f9fa; }}
        .file-link {{
            color: #0066cc;
            text-decoration: none;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 0.85rem;
            word-break: break-all;
            border-bottom: 1px dotted #0066cc;
        }}
        .badge {{
            display: inline-block;
            background: #f3f4f6;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.8rem;
            font-weight: 600;
        }}
        .badge.blocking {{ background: #fee2e2; color: #991b1b; }}
        .badge.non-blocking {{ background: #f3f4f6; color: #374151; }}
        .reasons {{ font-size: 0.85rem; color: #4b5563; }}
        .footer {{
            background: #f8f9fa;
            padding: 1.5rem 2rem;
            text-align: center;
            color: #6c757d;
            font-size: 0.9rem;
            border-top: 1px solid #e9ecef;
        }}
        .no-violations {{ text-align: center; padding: 3rem; color: #6c757d; }}
        .no-violations h3 {{ margin-bottom: 0.5rem; color: #059669; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📁 Forbidden Check Report</h1>
            <p>Результаты проверки расширений и языков файлов в репозитории</p>
        </div>
        <div class="meta-info">
            <div class="meta-basic">
                <div class="meta-item">
                    <span class="meta-label">📁 Проект:</span>
                    <span class="meta-value">{project_name}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">🔗 Репозиторий:</span>
                    <span class="meta-value">{project_repo_url}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">⚙️ Коммит:</span>
                    <span class="meta-value">{repo_commit}</span>
                </div>
            </div>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number">{scan_date}</div>
                    <div class="stat-label">🕒 Дата сканирования</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{files_scanned}</div>
                    <div class="stat-label">📂 Файлов просканировано</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{total_violations}</div>
                    <div class="stat-label">⚠️ Нарушений найдено</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{blocking_count}</div>
                    <div class="stat-label">🛑 Blocking</div>
                </div>
            </div>
        </div>
        <div class="violations-section">
            <h2>🔍 Обнаруженные нарушения</h2>
"""

    if not violations:
        html_content += """
            <div class="no-violations">
                <h3>✅ Нарушения не обнаружены</h3>
                <p>Сканирование не выявило запрещённых файлов.</p>
            </div>
        """
    else:
        for category, category_violations in sorted(violations_by_category.items()):
            type_id = re.sub(r"[^a-zA-Z0-9_]", "_", category)
            type_id_js = sanitize_js_string(type_id)
            html_content += f"""
            <div class="type-group">
                <div class="type-header" onclick="toggleTypeGroup('{type_id_js}')">
                    <div class="type-header-content">
                        <div class="type-title">🏷️ {category}</div>
                        <div class="type-count">{len(category_violations)} нарушений</div>
                    </div>
                    <div class="collapse-indicator" id="indicator_{type_id}">Свернуть 🔽</div>
                </div>
                <div class="type-content expanded" id="content_{type_id}">
                    <table class="violations-table">
                        <thead>
                            <tr>
                                <th>📁 Path</th>
                                <th>📎 Extension</th>
                                <th>🌐 Language</th>
                                <th>📦 Size</th>
                                <th>⚠️ Level</th>
                                <th>📝 Reasons</th>
                            </tr>
                        </thead>
                        <tbody>
            """

            for violation in category_violations:
                path = sanitize_input((violation.path or "").replace("/devzone_repository/", ""))
                extension = sanitize_input(violation.extension or "—")
                language = sanitize_input(violation.language or "—")
                size_text = sanitize_input(_format_file_size(violation.size))
                level_class = "blocking" if violation.is_blocking else "non-blocking"
                level_text = "Blocking" if violation.is_blocking else "Non-blocking"
                reasons = _parse_violation_reasons(violation.violation_reasons)
                reasons_html = "<br>".join(f"• {sanitize_input(reason)}" for reason in reasons) or "—"
                file_url = sanitize_url(
                    _build_file_url(project.repo_url or "", scan.repo_commit or "", hub_type, violation.path or "")
                )

                html_content += f"""
                            <tr>
                                <td>
                                    <a href="{file_url}" target="_blank" rel="noopener noreferrer" class="file-link">{path}</a>
                                </td>
                                <td><span class="badge">{extension}</span></td>
                                <td>{language}</td>
                                <td>{size_text}</td>
                                <td><span class="badge {level_class}">{level_text}</span></td>
                                <td class="reasons">{reasons_html}</td>
                            </tr>
                """

            html_content += """
                        </tbody>
                    </table>
                </div>
            </div>
            """

    current_time = sanitize_input(datetime.now().strftime("%d.%m.%Y %H:%M"))
    html_content += f"""
        </div>
        <div class="footer">
            <p>📋 Отчет сгенерирован с помощью Secrets Scanner (Forbidden Check)</p>
            <p class="time-left">🕒 {current_time}</p>
        </div>
    </div>
    <script>
        function toggleTypeGroup(typeId) {{
            if (!typeId || typeof typeId !== 'string') return;
            typeId = typeId.replace(/[^a-zA-Z0-9_]/g, '_');
            const content = document.getElementById('content_' + typeId);
            const indicator = document.getElementById('indicator_' + typeId);
            if (!content || !indicator) return;
            if (content.classList.contains('expanded')) {{
                content.classList.remove('expanded');
                content.classList.add('collapsed');
                indicator.textContent = 'Развернуть ▶️';
            }} else {{
                content.classList.remove('collapsed');
                content.classList.add('expanded');
                indicator.textContent = 'Свернуть 🔽';
            }}
        }}
    </script>
</body>
</html>
    """

    return html_content
