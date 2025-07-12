from fastapi.templating import Jinja2Templates
from services.template_filters import setup_template_filters

# Create a single templates instance with all filters configured
templates = Jinja2Templates(directory="templates")
setup_template_filters(templates)