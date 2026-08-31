"""The single assistant panel, registered on the Sextant dashboard."""

import horizon
from django.utils.translation import gettext_lazy as _

from sextant.dashboard import Sextant


class Assistant(horizon.Panel):
    name = _("Assistant")
    slug = "assistant"
    # URLs for this panel live in sextant/urls.py
    urls = "sextant.urls"


Sextant.register(Assistant)
