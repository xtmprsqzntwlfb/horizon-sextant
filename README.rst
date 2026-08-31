========================
horizon-sextant
========================

A **read-only AI ops assistant** packaged as an OpenStack Horizon plugin. It adds
a *Sextant* dashboard with a single *Assistant* panel — a chat box where operators
ask questions in natural language. The agent inspects the cloud through a handful
of read-only tools built on ``openstack_dashboard.api`` and streams its answer back.

Design goals
============

* **Encapsulated** — a standalone dashboard/panel plugin; it does not patch or
  modify any existing Horizon dashboard.
* **Read-only** — the tools only *list* and *describe*. The agent never creates,
  modifies, or deletes anything. When a fix is needed it points the operator to
  the Horizon panel to do it themselves.
* **Auth inherited** — every OpenStack call runs with the logged-in operator's
  Keystone token and scope (the Django ``request``). RBAC/policy is enforced
  exactly as in the rest of Horizon; the agent can't read what the operator
  can't.
* **Key stays server-side** — the Anthropic API key lives in Horizon settings and
  is never exposed to the browser.

What's included
===============

Tools (all read-only):

* ``list_instances`` — servers across the cloud, with light filtering.
* ``describe_instance`` — deep detail: state, fault, ports, volumes, SGs.
* ``check_instance_connectivity`` — walks ports/floating IPs/SG rules and flags
  likely reachability gaps (the flagship "why can't I reach X?" workflow).
* ``list_hypervisors`` — per-host vCPU/RAM capacity (admin).
* ``list_networks`` — Neutron networks.

Installation
============

1. Install the package into the same environment as Horizon::

     pip install .

2. Enable the plugin by copying the enabled file into your Horizon deployment::

     cp sextant/enabled/_9010_sextant.py \
        <horizon>/openstack_dashboard/local/enabled/

3. Configure credentials in ``local_settings.py``::

     SEXTANT = {
         "api_key": "sk-ant-...",      # or set ANTHROPIC_API_KEY in the env
         "model": "claude-opus-5",     # optional
         "effort": "high",             # low | medium | high | xhigh | max
         "max_iterations": 8,
     }

4. Restart the Horizon web server. The *Sextant* dashboard appears in the nav.

Requirements & assumptions
==========================

* Targets a **recent Horizon** (Django 4.2-era). The ``api.*`` call signatures
  and template blocks (``base.html`` → ``main``) follow current-release
  conventions; verify against your exact version.
* The streaming endpoint holds a WSGI worker open for the duration of a turn
  (SSE). For anything beyond a pilot, run Horizon under an async-capable server
  or move the agent loop to a background worker and stream from a queue.
* An Anthropic API key with access to the configured model.

Security notes
==============

* Tenant-controlled strings (resource names, metadata, image properties) are
  treated as untrusted data in the system prompt to blunt prompt injection.
* The browser may only send user/assistant **text** turns; tool calls and their
  results are produced server-side and never trusted from the client.

Roadmap
=======

* Context-awareness (an "Explain this" action on existing detail pages).
* Metrics-backed capacity reasoning (Gnocchi / Prometheus).
* Guided *mutation with human-in-the-loop* once the read-only slice is trusted.
