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

"""Test harness: stub the heavy Horizon/Django/Anthropic deps.

The plugin normally runs inside a Horizon deployment. To unit-test the agent
loop and tool dispatch without a live cloud (or any of those packages
installed), we register minimal stub modules in ``sys.modules`` *before* the
plugin is imported. Tests then inject behavior via monkeypatch.
"""

import os
import sys
import types
from types import SimpleNamespace

import pytest

# Make ``sextant`` importable (repo root == parent of this tests/ dir).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# --------------------------------------------------------------------------- #
# Stub modules (installed once, at import time)
# --------------------------------------------------------------------------- #
def _install_stubs():
    # django.conf.settings — bare namespace; tests set SEXTANT on it.
    django = types.ModuleType("django")
    django_conf = types.ModuleType("django.conf")
    django_conf.settings = SimpleNamespace()
    sys.modules.setdefault("django", django)
    sys.modules.setdefault("django.conf", django_conf)

    # anthropic — only Anthropic() is referenced (inside get_client, which the
    # loop tests monkeypatch away), so a no-op class suffices for import.
    anthropic_mod = types.ModuleType("anthropic")

    class _Anthropic:
        def __init__(self, *a, **k):
            pass

    anthropic_mod.Anthropic = _Anthropic
    sys.modules.setdefault("anthropic", anthropic_mod)

    # openstack_dashboard.api with empty nova/neutron namespaces.
    osd = types.ModuleType("openstack_dashboard")
    api_mod = types.ModuleType("openstack_dashboard.api")
    api_mod.nova = SimpleNamespace()
    api_mod.neutron = SimpleNamespace()
    osd.api = api_mod
    sys.modules.setdefault("openstack_dashboard", osd)
    sys.modules.setdefault("openstack_dashboard.api", api_mod)


_install_stubs()


# --------------------------------------------------------------------------- #
# Shared fixtures / helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def api():
    """The stubbed ``openstack_dashboard.api`` module (nova/neutron)."""
    from openstack_dashboard import api as api_mod
    # Reset between tests so leftover attrs don't leak.
    api_mod.nova = SimpleNamespace()
    api_mod.neutron = SimpleNamespace()
    return api_mod


def make_server(**overrides):
    """Build a fake Nova server object (supports hyphenated attr names)."""
    s = SimpleNamespace(
        id=overrides.get("id", "i-1"),
        name=overrides.get("name", "web01"),
        status=overrides.get("status", "ACTIVE"),
        tenant_id=overrides.get("tenant_id", "proj-1"),
        flavor=overrides.get("flavor", {"id": "m1.small"}),
        addresses=overrides.get("addresses", {}),
        fault=overrides.get("fault", None),
        security_groups=overrides.get("security_groups", []),
    )
    setattr(s, "OS-EXT-STS:power_state", overrides.get("power_state", 1))
    setattr(s, "OS-EXT-SRV-ATTR:host", overrides.get("host", "compute-1"))
    setattr(s, "os-extended-volumes:volumes_attached",
            overrides.get("volumes_attached", []))
    return s


# ---- Fake Anthropic client that replays a scripted set of turns ------------ #
class FakeStream:
    def __init__(self, texts, final):
        self._texts = list(texts)
        self._final = final

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def text_stream(self):
        return iter(self._texts)

    def get_final_message(self):
        return self._final


class FakeMessages:
    def __init__(self, turns):
        self._turns = turns
        self._i = 0

    def stream(self, **kwargs):
        turn = self._turns[self._i]
        self._i += 1
        return FakeStream(turn["texts"], turn["final"])


class FakeClient:
    def __init__(self, turns):
        self.messages = FakeMessages(turns)


def tool_use_block(block_id, name, inp):
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=inp)


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def final_message(stop_reason, content):
    return SimpleNamespace(stop_reason=stop_reason, content=content)
