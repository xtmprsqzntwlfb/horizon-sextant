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

"""Read-only tools the assistant can call, backed by ``openstack_dashboard.api``.

Every tool receives the live Horizon ``request`` object, so all OpenStack calls
run with the logged-in operator's Keystone token and scope. RBAC / policy is
therefore inherited automatically — the agent can never read anything the
operator couldn't read in the UI.

Each tool returns compact, LLM-friendly summaries (IDs + the few fields that
matter), not full API objects, to keep token cost and confusion down. Lists are
capped by ``MAX_ITEMS`` and report truncation explicitly.

NOTE: The exact ``api.*`` signatures vary slightly across Horizon releases.
These follow recent-release conventions; verify against your target version.
"""

import json
import logging

from openstack_dashboard import api

LOG = logging.getLogger(__name__)

MAX_ITEMS = 100


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _host_of(server):
    # Only populated for admin-scoped requests.
    return getattr(server, "OS-EXT-SRV-ATTR:host", None)


def _instance_url(server_id):
    # Admin instances detail panel. Adjust if you register the panel elsewhere.
    return "/admin/instances/%s/detail" % server_id


def _server_summary(server):
    return {
        "id": server.id,
        "name": server.name,
        "status": server.status,
        "power_state": getattr(server, "OS-EXT-STS:power_state", None),
        "host": _host_of(server),
        "project_id": getattr(server, "tenant_id", None),
        "flavor": (server.flavor or {}).get("id") if isinstance(
            getattr(server, "flavor", None), dict) else getattr(server, "flavor", None),
        "addresses": server.addresses,
        "fault": getattr(server, "fault", None),
        "horizon_url": _instance_url(server.id),
    }


# --------------------------------------------------------------------------- #
# Tool implementations
# --------------------------------------------------------------------------- #
def list_instances(request, project_id=None, status=None, host=None):
    """List servers across the cloud (admin scope) with light filtering."""
    search_opts = {"all_tenants": True}
    if project_id:
        search_opts["project_id"] = project_id
    if status:
        search_opts["status"] = status.upper()
    if host:
        search_opts["host"] = host

    servers, has_more = api.nova.server_list(request, search_opts=search_opts)
    summaries = [_server_summary(s) for s in servers[:MAX_ITEMS]]
    return {
        "count_returned": len(summaries),
        "truncated": bool(has_more) or len(servers) > MAX_ITEMS,
        "instances": summaries,
    }


def describe_instance(request, instance_id):
    """Deep view of one server: state, ports, volumes, security groups."""
    server = api.nova.server_get(request, instance_id)
    result = _server_summary(server)

    # Attached volumes (best-effort).
    try:
        vols = getattr(server, "os-extended-volumes:volumes_attached", []) or []
        result["attached_volume_ids"] = [v.get("id") for v in vols]
    except Exception as exc:  # noqa: BLE001
        result["attached_volume_ids"] = "error: %s" % exc

    # Neutron ports on this instance.
    try:
        ports = api.neutron.port_list(request, device_id=instance_id)
        result["ports"] = [
            {
                "id": p.id,
                "network_id": p.network_id,
                "status": p.status,
                "mac_address": getattr(p, "mac_address", None),
                "fixed_ips": getattr(p, "fixed_ips", None),
                "security_group_ids": getattr(p, "security_groups", None),
            }
            for p in ports
        ]
    except Exception as exc:  # noqa: BLE001
        result["ports"] = "error: %s" % exc

    # Security groups as reported by Nova.
    result["security_groups"] = [
        g.get("name") for g in (getattr(server, "security_groups", None) or [])
    ]
    return result


def check_instance_connectivity(request, instance_id):
    """Walk the L3 path for an instance and flag likely connectivity gaps.

    Correlates ports, floating IPs, and security-group ingress rules — the
    data an operator normally has to gather from 3-4 separate panels.
    """
    server = api.nova.server_get(request, instance_id)
    findings = {
        "instance_id": instance_id,
        "status": server.status,
        "addresses": server.addresses,
        "ports": [],
        "floating_ips": [],
        "observations": [],
    }

    if server.status != "ACTIVE":
        findings["observations"].append(
            "Instance is %s, not ACTIVE — connectivity issues may stem from the "
            "instance state itself." % server.status
        )

    try:
        ports = api.neutron.port_list(request, device_id=instance_id)
    except Exception as exc:  # noqa: BLE001
        findings["ports"] = "error: %s" % exc
        ports = []

    # Gather security group ingress rules referenced by the ports.
    sg_cache = {}
    for p in ports:
        sg_ids = getattr(p, "security_groups", []) or []
        for sg_id in sg_ids:
            if sg_id in sg_cache:
                continue
            try:
                sg = api.neutron.security_group_get(request, sg_id)
                sg_cache[sg_id] = [
                    {
                        "direction": r.get("direction"),
                        "protocol": r.get("protocol"),
                        "port_range_min": r.get("port_range_min"),
                        "port_range_max": r.get("port_range_max"),
                        "remote_ip_prefix": r.get("remote_ip_prefix"),
                    }
                    for r in (getattr(sg, "rules", None) or getattr(sg, "security_group_rules", []) or [])
                ]
            except Exception as exc:  # noqa: BLE001
                sg_cache[sg_id] = "error: %s" % exc
        findings["ports"].append({
            "id": p.id,
            "status": p.status,
            "fixed_ips": getattr(p, "fixed_ips", None),
            "security_group_ids": sg_ids,
        })
        if p.status != "ACTIVE":
            findings["observations"].append(
                "Port %s is %s (not ACTIVE)." % (p.id, p.status))

    findings["security_group_rules"] = sg_cache

    # Floating IPs (project scope of the operator's token).
    try:
        fips = api.neutron.tenant_floating_ip_list(request)
        for fip in fips:
            fixed = getattr(fip, "fixed_ip", None)
            if fixed and any(
                fixed in json.dumps(getattr(p, "fixed_ips", []) or [])
                for p in ports
            ):
                findings["floating_ips"].append({
                    "id": fip.id,
                    "floating_ip_address": getattr(fip, "ip", None) or getattr(fip, "floating_ip_address", None),
                    "fixed_ip": fixed,
                })
    except Exception as exc:  # noqa: BLE001
        findings["floating_ips"] = "error: %s" % exc

    if not findings["floating_ips"]:
        findings["observations"].append(
            "No floating IP is associated with this instance's ports — it is not "
            "reachable from outside the tenant network unless reached via a router "
            "or VPN.")

    return findings


def list_hypervisors(request):
    """Per-host capacity: vCPU/RAM allocation vs. total (admin only)."""
    try:
        hypervisors = api.nova.hypervisor_list(request)
    except Exception as exc:  # noqa: BLE001
        return {"error": "hypervisor_list failed (admin only?): %s" % exc}

    hosts = []
    for h in hypervisors[:MAX_ITEMS]:
        hosts.append({
            "hypervisor_hostname": getattr(h, "hypervisor_hostname", None),
            "state": getattr(h, "state", None),
            "vcpus_used": getattr(h, "vcpus_used", None),
            "vcpus": getattr(h, "vcpus", None),
            "memory_mb_used": getattr(h, "memory_mb_used", None),
            "memory_mb": getattr(h, "memory_mb", None),
            "running_vms": getattr(h, "running_vms", None),
        })
    return {"count": len(hosts), "hypervisors": hosts}


def list_networks(request):
    """List Neutron networks visible to the operator."""
    networks = api.neutron.network_list(request)
    return {
        "count": len(networks),
        "networks": [
            {
                "id": n.id,
                "name": n.name,
                "status": getattr(n, "status", None),
                "is_external": getattr(n, "router:external", None),
                "shared": getattr(n, "shared", None),
                "subnet_ids": getattr(n, "subnets", None),
                "project_id": getattr(n, "tenant_id", None),
            }
            for n in networks[:MAX_ITEMS]
        ],
        "truncated": len(networks) > MAX_ITEMS,
    }


# --------------------------------------------------------------------------- #
# Registry: tool specs (sent to Claude) + dispatch
# --------------------------------------------------------------------------- #
_HANDLERS = {
    "list_instances": list_instances,
    "describe_instance": describe_instance,
    "check_instance_connectivity": check_instance_connectivity,
    "list_hypervisors": list_hypervisors,
    "list_networks": list_networks,
}

TOOL_SPECS = [
    {
        "name": "list_instances",
        "description": (
            "List server instances across the cloud (admin scope). Returns id, "
            "name, status, host, project, flavor, and addresses. Use filters to "
            "narrow large clouds; results are capped and report truncation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Filter by project/tenant ID."},
                "status": {"type": "string", "description": "Filter by status, e.g. ACTIVE, ERROR, SHUTOFF."},
                "host": {"type": "string", "description": "Filter by compute host name."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "describe_instance",
        "description": (
            "Deep detail for one instance: state, fault message, attached "
            "volumes, Neutron ports, and security groups. Use after list_instances."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"instance_id": {"type": "string"}},
            "required": ["instance_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_instance_connectivity",
        "description": (
            "Diagnose why an instance may be unreachable: walks its ports, "
            "floating IPs, and security-group ingress rules and returns "
            "observations about likely gaps. Best first tool for 'can't reach X'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"instance_id": {"type": "string"}},
            "required": ["instance_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_hypervisors",
        "description": (
            "Per-compute-host capacity: vCPU and RAM used vs. total, state, and "
            "running VM count. Admin only. Use for capacity questions."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_networks",
        "description": "List Neutron networks (id, name, external/shared flags, subnets).",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def execute_tool(request, name, tool_input):
    """Dispatch a tool call. Returns {'content': str, 'is_error': bool}."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"content": "Unknown tool: %s" % name, "is_error": True}
    try:
        result = handler(request, **(tool_input or {}))
        return {"content": json.dumps(result, default=str), "is_error": False}
    except Exception as exc:  # noqa: BLE001
        LOG.exception("Tool %s failed", name)
        return {"content": "Tool %s failed: %s" % (name, exc), "is_error": True}
