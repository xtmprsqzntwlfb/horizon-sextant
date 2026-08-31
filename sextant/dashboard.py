"""A self-contained dashboard so the plugin doesn't touch existing dashboards."""

import horizon
from django.utils.translation import gettext_lazy as _


class Sextant(horizon.Dashboard):
    name = _("Sextant")
    slug = "sextant"
    panels = ("assistant",)
    default_panel = "assistant"
    # Operator-facing: require an admin-ish role. Adjust to your policy.
    policy_rules = (("identity", "identity:get_user"),)


horizon.register(Sextant)
