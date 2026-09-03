===============
horizon-sextant
===============

A **read-only AI ops assistant** packaged as an OpenStack Horizon plugin. It adds
a *Sextant* dashboard with a single *Assistant* panel — a chat box where operators
ask questions in natural language. The agent inspects the cloud through a handful
of read-only tools built on ``openstack_dashboard.api`` and streams its answer back.

Design goals
============

* **Encapsulated** — a standalone dashboard/panel plugin; it does not patch or
  modify any existing Horizon dashboard.
* **Read-only** — the tools only *list* and *describe*. The agent never creates,
  modifies or deletes anything. When a fix is needed it points the operator to
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

These steps assume a **source checkout of Horizon** (e.g. devstack) with the
``horizon`` and ``horizon-sextant`` trees side by side::

    parent/
    ├── horizon/            # the Horizon source tree (has manage.py)
    └── horizon-sextant/    # this repo

A Horizon plugin is *not* copied into the ``horizon`` tree. ``pip install``
puts the ``sextant`` package on Horizon's Python path; a single "enabled" file
wires it into the dashboard, and Horizon imports the rest from the installed
package. The only file that lands in the ``horizon`` tree is that enabled file.

Every command must use **the Python environment that runs your Horizon**. If
your checkout uses a virtualenv, activate it first; otherwise use whatever
``python``/``pip`` you launch Horizon with.

You also need an **Anthropic API key** with access to the configured model.

Run these from the parent directory that holds both trees.

1. **Install the plugin into Horizon's Python environment**::

     cd horizon-sextant
     pip install .

   Then confirm it imported into the right place::

     python -c "import sextant, sextant.agent.loop; print('ok', sextant.__file__)"

   You should see ``ok`` and a path ending in ``.../site-packages/sextant/__init__.py``.
   If it errors, the wrong ``pip``/``python`` was used — fix that before going on.

   (Use ``pip install -e .`` instead if you want edits in ``horizon-sextant`` to
   take effect on restart without reinstalling.)

2. **Register the plugin** — copy the one enabled file into Horizon's local
   enabled directory::

     cp sextant/enabled/_9010_sextant.py \
        ../horizon/openstack_dashboard/local/enabled/

   (The ``_9010_`` prefix controls load order; leave it unless it collides with
   an existing file.)

3. **Configure the API key** — add to
   ``../horizon/openstack_dashboard/local/local_settings.py``::

     SEXTANT = {
         "api_key": "sk-ant-...",      # or omit and set ANTHROPIC_API_KEY in the env
         "model": "claude-opus-5",     # optional; this is the default
         "effort": "high",             # optional: low | medium | high | xhigh | max
         "max_iterations": 8,          # optional: tool-call rounds per question
     }

   The key stays server-side and is never sent to the browser. If you prefer,
   drop ``api_key`` and export ``ANTHROPIC_API_KEY`` in the web server's
   environment instead.

4. **Restart Horizon.**

   * Dev server: stop it and re-run ``python manage.py runserver`` from the
     ``horizon`` dir.
   * Apache/mod_wsgi (packaged installs)::

       sudo systemctl restart httpd          # RHEL/CentOS/Fedora
       # or
       sudo systemctl restart apache2        # Ubuntu/Debian

   No ``collectstatic``/``compress`` step is needed — the panel's CSS and JS are
   inlined in its Django template, so it ships no separate static assets.

5. **Verify.** Log in to Horizon as an admin-capable user. A **Sextant**
   dashboard appears in the left nav with an **Assistant** panel. Open it and
   ask, e.g., *"list all instances in ERROR state"*. If the tools error, see the
   note under Requirements about ``api.*`` version differences.

Packaged installs (RHEL/Ubuntu) follow the same steps; the paths differ —
``horizon`` lives at ``/usr/share/openstack-dashboard`` and local settings at
``/etc/openstack-dashboard/local_settings``.

Upgrading or uninstalling
-------------------------

* **Upgrade**: ``pip install --upgrade .`` and restart Horizon.
* **Uninstall**: remove
  ``../horizon/openstack_dashboard/local/enabled/_9010_sextant.py``,
  ``pip uninstall horizon-sextant``, and restart Horizon.

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
