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

"""The single assistant panel, registered on the Sextant dashboard."""

import horizon
from django.utils.translation import gettext_lazy as _

from sextant.dashboard import Sextant


class Assistant(horizon.Panel):
    name = _("Assistant")
    slug = "assistant"
    # URLs for this panel live in sextant/panel_urls.py. It must NOT be named
    # sextant/urls.py: the dashboard package is "sextant", and Horizon would
    # then pick that module up as the *dashboard's* own default URLs too,
    # sharing (and mutating) the same urlpatterns list and creating a
    # self-referential include -> RecursionError at startup.
    urls = "sextant.panel_urls"


Sextant.register(Assistant)
