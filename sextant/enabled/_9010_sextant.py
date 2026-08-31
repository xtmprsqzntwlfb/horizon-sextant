"""Horizon plugin registration for the Sextant dashboard.

Copy (or symlink) this file into your Horizon deployment's
``openstack_dashboard/local/enabled/`` directory, and ensure ``sextant``
is importable (pip install the package). Horizon auto-discovers ``dashboard.py``
and ``panel.py`` in the added app.
"""

# The slug of the dashboard this file configures.
DASHBOARD = "sextant"

# Not the default landing dashboard.
DEFAULT = False

# Add our app so Horizon imports its dashboard.py / panel.py and serves static.
ADD_INSTALLED_APPS = ["sextant"]

# Serve the panel's static assets.
AUTO_DISCOVER_STATIC_FILES = True
