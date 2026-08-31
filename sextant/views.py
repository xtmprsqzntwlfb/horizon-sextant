"""Panel views: the chat page and the SSE streaming endpoint.

The stream endpoint runs the agentic loop and pushes events to the browser as
Server-Sent Events. It holds the request open for the duration of the turn —
fine for a first slice; for production behind a small WSGI worker pool, move the
loop to a background worker (Celery / a thread) and stream from a queue.
"""

import json
import logging

from django.http import HttpResponseBadRequest, StreamingHttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from horizon import views

from sextant.agent.loop import run_agent

LOG = logging.getLogger(__name__)

# Guardrails on what the browser may send.
MAX_MESSAGES = 40
MAX_CHARS = 20000


class IndexView(views.HorizonTemplateView):
    template_name = "sextant/index.html"
    page_title = "Sextant Assistant"


def _sse(event):
    """Serialize one event dict as a Server-Sent Event frame."""
    return "data: %s\n\n" % json.dumps(event)


def _sanitize_history(raw):
    """Validate the client-supplied conversation into API message shape.

    Only user/assistant text turns are accepted from the client. Tool calls and
    their results are produced server-side inside the loop and are never trusted
    from the browser.
    """
    if not isinstance(raw, list) or not raw:
        raise ValueError("messages must be a non-empty list")
    if len(raw) > MAX_MESSAGES:
        raise ValueError("too many messages")

    messages = []
    total = 0
    for item in raw:
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            raise ValueError("each message needs role user|assistant and string content")
        total += len(content)
        if total > MAX_CHARS:
            raise ValueError("conversation too long")
        messages.append({"role": role, "content": content})

    if messages[-1]["role"] != "user":
        raise ValueError("last message must be from the user")
    return messages


@require_POST
def stream(request):
    """POST {messages: [{role, content}, ...]} -> text/event-stream."""
    try:
        payload = json.loads(request.body.decode("utf-8"))
        messages = _sanitize_history(payload.get("messages"))
    except (ValueError, json.JSONDecodeError) as exc:
        return HttpResponseBadRequest("Invalid request: %s" % exc)

    def event_stream():
        try:
            for event in run_agent(request, messages):
                yield _sse(event)
        except Exception as exc:  # noqa: BLE001
            LOG.exception("Agent stream crashed")
            yield _sse({"type": "error", "message": "Internal error: %s" % exc})

    response = StreamingHttpResponse(
        event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # disable nginx buffering
    return response


# Ensure the CSRF cookie is set when the page loads so the JS fetch can send it.
IndexView.dispatch = ensure_csrf_cookie(IndexView.dispatch)
