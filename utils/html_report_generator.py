
import html
from datetime import datetime

def generate_html_report(scan, project, secrets, HubType):
    """Generate HTML report for scan results"""
    
    # Count statistics
    total_secrets = len(secrets)
    
    # Group secrets by type
    secrets_by_type = {}
    for secret in secrets:
        if secret.type not in secrets_by_type:
            secrets_by_type[secret.type] = []
        secrets_by_type[secret.type].append(secret)
    
    # Format scan date
    scan_date = "Unknown"
    if scan.completed_at:
        scan_date = scan.completed_at.strftime('%d.%m.%Y %H:%M')
    
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Отчет Secrets Scan {project.name}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
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
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
            font-weight: 700;
        }}
        
        .header p {{
            font-size: 1.1rem;
            opacity: 0.9;
        }}
        
        .meta-info {{
            background: #f8f9fa;
            padding: 1.5rem 2rem;
            border-bottom: 1px solid #e9ecef;
        }}
        
        .meta-basic {{
            margin-bottom: 1.5rem;
        }}
        
        .meta-item {{
            display: flex;
            margin-bottom: 0.75rem;
        }}
        
        .meta-item:last-child {{
            margin-bottom: 0;
        }}
        
        .meta-label {{
            font-weight: 600;
            color: #6c757d;
            min-width: 180px;
            flex-shrink: 0;
        }}
        
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
        }}
        
        .stat-card {{
            background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 1rem;
            text-align: center;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        
        .stat-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        
        .stat-number {{
            font-size: 1.5rem;
            font-weight: 600;
            color: #495057;
            margin-bottom: 0.5rem;
        }}
        
        .stat-label {{
            font-size: 0.9rem;
            color: #6c757d;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .secrets-section {{
            padding: 2rem;
        }}
        
        .type-group {{
            margin-bottom: 2rem;
        }}
        
        .type-header {{
            background: #f8f9fa;
            padding: 1rem 1.5rem;
            border-left: 4px solid #6c757d;
            border-radius: 0 8px 8px 0;
            cursor: pointer;
            transition: all 0.2s ease;
            user-select: none;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .type-header:hover {{
            background: #e9ecef;
            border-left-color: #495057;
        }}
        
        .type-header-content {{
            flex: 1;
        }}
        
        .type-title {{
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 0.25rem;
        }}
        
        .type-count {{
            color: #6c757d;
            font-size: 0.9rem;
        }}
        
        .collapse-indicator {{
            font-size: 1.2rem;
            color: #6c757d;
            transition: transform 0.2s ease;
        }}
        
        .type-content {{
            overflow: hidden;
            transition: max-height 0.3s ease;
        }}
        
        .type-content.collapsed {{
            max-height: 0;
        }}
        
        .type-content.expanded {{
            max-height: none;
        }}
        
        .secrets-table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin-top: 1rem;
        }}
        
        .secrets-table th {{
            background: #495057;
            color: white;
            padding: 1rem;
            text-align: left;
            font-weight: 600;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .secrets-table td {{
            padding: 1rem;
            border-bottom: 1px solid #e9ecef;
            vertical-align: top;
        }}
        
        .secrets-table tr:last-child td {{
            border-bottom: none;
        }}
        
        .secrets-table tr:hover {{
            background: #f8f9fa;
        }}
        
        .secret-value {{
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            background: #f8f9fa;
            padding: 0.5rem;
            border-radius: 4px;
            border: 1px solid #e9ecef;
            word-break: break-all;
            font-size: 0.85rem;
            max-width: 200px;
        }}
        
        .file-link {{
            color: #0066cc;
            text-decoration: none;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 0.85rem;
            word-break: break-all;
            border-bottom: 1px dotted #0066cc;
            transition: all 0.2s ease;
        }}
        
        .file-link:hover {{
            background: #e3f2fd;
            padding: 0.25rem;
            border-radius: 4px;
            border-bottom: 1px solid #0066cc;
        }}
        
        .line-number {{
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            background: #e8f5e8;
            color: #2e7d32;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-weight: 600;
            font-size: 0.9rem;
        }}
        
        .footer {{
            background: #f8f9fa;
            padding: 1.5rem 2rem;
            text-align: center;
            color: #6c757d;
            font-size: 0.9rem;
            border-top: 1px solid #e9ecef;
        }}
        
        .no-secrets {{
            text-align: center;
            padding: 3rem;
            color: #6c757d;
        }}
        
        .no-secrets h3 {{
            margin-bottom: 0.5rem;
            color: #28a745;
        }}
        
        @media print {{
            body {{ background: white; padding: 0; }}
            .container {{ box-shadow: none; }}
            .secrets-table {{ box-shadow: none; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔒 Отчет Secrets Scanner</h1>
            <p>Результаты автоматизированного сканирования репозитория на наличие нескрытых секретов</p>
        </div>
        
        <div class="meta-info">
            <div class="meta-basic">
                <div class="meta-item">
                    <span class="meta-label">📁 Проект:</span>
                    <span class="meta-value">{project.name}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">🔗 Репозиторий:</span>
                    <span class="meta-value">{project.repo_url}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">⚙️ Коммит:</span>
                    <span class="meta-value">{scan.repo_commit or 'Unknown'}</span>
                </div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number">{scan_date}</div>
                    <div class="stat-label">🕒 Дата сканирования</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{scan.files_scanned or 'Unknown'}</div>
                    <div class="stat-label">📂 Файлов просканировано</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{total_secrets}</div>
                    <div class="stat-label">🔍 Секретов найдено</div>
                </div>
            </div>
        </div>
        
        <div class="secrets-section">
            <h2>🔍 Обнаруженные секреты</h2>
"""
    
    if not secrets:
        html_content += """
            <div class="no-secrets">
                <h3>✅ Секреты не обнаружены!</h3>
                <p>Сканирование не выявило потенциальных проблем.</p>
            </div>
        """
    else:
        for secret_type, type_secrets in secrets_by_type.items():
            type_id = secret_type.replace(' ', '_').replace('-', '_')
            html_content += f"""
            <div class="type-group">
                <div class="type-header" onclick="toggleTypeGroup('{type_id}')">
                    <div class="type-header-content">
                        <div class="type-title">🏷️ {secret_type}</div>
                        <div class="type-count">{len(type_secrets)} секретов найдено</div>
                    </div>
                    <div class="collapse-indicator" id="indicator_{type_id}">▼</div>
                </div>
                
                <div class="type-content expanded" id="content_{type_id}">
                    <table class="secrets-table">
                        <thead>
                            <tr>
                                <th>🔑 Значение секрета</th>
                                <th>📁 Путь к файлу</th>
                                <th>📍 Номер строки</th>
                            </tr>
                        </thead>
                        <tbody>
            """
            
            for secret in type_secrets:
                # Build file URL based on hub type
                if HubType == 'Azure':
                    start_column = 1
                    end_column = len(secret.secret) + 1
                    file_url = f"{project.repo_url}?path={secret.path}&version=GC{scan.repo_commit}&line={secret.line}&lineEnd={secret.line}&lineStartColumn={start_column}&lineEndColumn={end_column}&_a=contents"
                else:
                    file_url = f"{project.repo_url}/blob/{scan.repo_commit}{secret.path}?plain=1#L{secret.line}"
                
                # Mask secret value (show only first 4 characters)
                masked_secret = secret.secret[:4] + '*' * max(0, len(secret.secret) - 4)
                
                html_content += f"""
                            <tr>
                                <td>
                                    <div class="secret-value">{html.escape(masked_secret)}</div>
                                </td>
                                <td>
                                    <a href="{file_url}" target="_blank" class="file-link">
                                        {html.escape(secret.path)}
                                    </a>
                                </td>
                                <td>
                                    <span class="line-number">{secret.line}</span>
                                </td>
                            </tr>
                """
            
            html_content += """
                        </tbody>
                    </table>
                </div>
            </div>
            """
    
    html_content += f"""
        </div>
        
        <div class="footer">
            <p>🔍 Отчет сгенерирован с помощью Secrets Scanner • {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
            <p>⚠️ Данный отчет может содержать конфиденциальную информацию.</p>
        </div>
    </div>

    <script>
        function toggleTypeGroup(typeId) {{
            const content = document.getElementById('content_' + typeId);
            const indicator = document.getElementById('indicator_' + typeId);
            
            if (content.classList.contains('expanded')) {{
                content.classList.remove('expanded');
                content.classList.add('collapsed');
                indicator.textContent = '▶';
            }} else {{
                content.classList.remove('collapsed');
                content.classList.add('expanded');
                indicator.textContent = '▼';
            }}
        }}
    </script>
</body>
</html>
    """
    
    return html_content