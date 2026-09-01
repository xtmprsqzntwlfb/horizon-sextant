# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

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
