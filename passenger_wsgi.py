"""Entry point for cPanel "Setup Python App" (Phusion Passenger).

Passenger imports `application` from this file in the app root. Settings
come from the environment variables set in the cPanel app screen, or from a
.env file next to this file (never committed).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
