import json
import urllib.parse
from datetime import datetime
from config import get_full_url

def tojson_filter(obj):
    """Convert object to JSON string"""
    if obj is None:
        return json.dumps("")
    try:
        return json.dumps(obj)
    except (TypeError, ValueError):
        return json.dumps("")

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