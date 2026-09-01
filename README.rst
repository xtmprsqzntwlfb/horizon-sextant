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

Prerequisites
-------------

* A running OpenStack **Horizon** deployment you can restart (devstack, or a
  packaged install).
* Shell access to the host, and permission to edit Horizon's settings and
  restart its web server.
* The **Python environment Horizon runs under** (its virtualenv, or the system
  Python for packaged installs). Every command below must use *that* interpreter
  and pip — installing Sextant into a different environment will not work.
* An **Anthropic API key** with access to the configured model.

Throughout, two paths depend on your deployment. Find yours before you start:

* ``<horizon-src>`` — the Horizon source tree containing ``manage.py`` and the
  ``openstack_dashboard/`` package.

  * devstack: ``/opt/stack/horizon``
  * packaged (RHEL/CentOS): ``/usr/share/openstack-dashboard``
  * packaged (Ubuntu/Debian): ``/usr/share/openstack-dashboard``

* ``<local-settings>`` — Horizon's editable settings file.

  * devstack: ``/opt/stack/horizon/openstack_dashboard/local/local_settings.py``
  * packaged (RHEL): ``/etc/openstack-dashboard/local_settings``
  * packaged (Ubuntu): ``/etc/openstack-dashboard/local_settings.py``

Steps
-----

1. **Install the package into Horizon's Python environment.** From this repo's
   root (activate Horizon's virtualenv first if it has one)::

     pip install .

2. **Register the plugin.** Horizon auto-discovers plugins from "enabled" files.
   Copy Sextant's into Horizon's local enabled directory::

     cp sextant/enabled/_9010_sextant.py \
        <horizon-src>/openstack_dashboard/local/enabled/

   (The ``_9010_`` prefix controls load order; leave it unless it collides with
   an existing file.)

3. **Configure the API key.** Add to ``<local-settings>``::

     SEXTANT = {
         "api_key": "sk-ant-...",      # or omit and set ANTHROPIC_API_KEY in the env
         "model": "claude-opus-5",     # optional; this is the default
         "effort": "high",             # optional: low | medium | high | xhigh | max
         "max_iterations": 8,          # optional: tool-call rounds per question
     }

   The key stays server-side and is never sent to the browser. If you prefer,
   drop ``api_key`` and export ``ANTHROPIC_API_KEY`` in the web server's
   environment instead.

4. **Collect and compress static assets** so the panel's JS/CSS are served.
   Run from ``<horizon-src>`` with Horizon's interpreter::

     cd <horizon-src>
     python manage.py collectstatic --noinput
     python manage.py compress --force

   (Skipping this is the most common reason the panel loads blank.)

5. **Restart the Horizon web server.** Whichever your deployment uses::

     sudo systemctl restart httpd          # RHEL/CentOS/Fedora (Apache)
     # or
     sudo systemctl restart apache2        # Ubuntu/Debian (Apache)

6. **Verify.** Log in to Horizon as an admin-capable user. A **Sextant**
   dashboard appears in the left nav with an **Assistant** panel. Open it and
   ask, e.g., *"list all instances in ERROR state"*. If the tools error, see the
   note under Requirements about ``api.*`` version differences.

Upgrading or uninstalling
-------------------------

* **Upgrade**: ``pip install --upgrade .``, then re-run step 4 and restart.
* **Uninstall**: remove ``<horizon-src>/openstack_dashboard/local/enabled/_9010_sextant.py``,
  ``pip uninstall horizon-sextant``, re-run step 4, and restart.

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
