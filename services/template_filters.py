import json
import urllib.parse
from datetime import datetime
from config import get_full_url

def escape_json_for_html_script(json_str: str) -> str:
    """Prevent </script> breakout when JSON is embedded in HTML pages."""
    return (
        json_str
        .replace('<', '\\u003c')
        .replace('>', '\\u003e')
        .replace('&', '\\u0026')
        .replace('\u2028', '\\u2028')
        .replace('\u2029', '\\u2029')
    )

def json_for_html_script(obj):
    """Serialize object to JSON safe for <script type=\"application/json\"> blocks."""
    if obj is None:
        json_str = json.dumps("")
    else:
        try:
            json_str = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
        except (TypeError, ValueError):
            json_str = json.dumps("")
    return escape_json_for_html_script(json_str)

def tojson_filter(obj):
    """Convert object to JSON string safe for HTML embedding."""
    return json_for_html_script(obj)

def datetime_filter(timestamp):
    """Format timestamp to readable datetime string"""
    if timestamp:
        return datetime.fromtimestamp(timestamp).strftime('%d.%m.%Y %H:%M:%S')
    return 'Unknown'

def urldecode_filter(text):
    """URL decode text"""
    if text:
        return urllib.parse.unquote(text)
    return ''

def setup_template_filters(templates):
    """Setup all template filters and globals"""
    templates.env.filters['tojson'] = tojson_filter
    templates.env.filters['strftime'] = datetime_filter
    templates.env.filters['urldecode'] = urldecode_filter
    templates.env.globals['get_full_url'] = get_full_url