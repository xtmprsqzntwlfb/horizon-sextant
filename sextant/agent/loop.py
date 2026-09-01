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

"""The read-only agentic loop.

``run_agent`` is a generator that yields event dicts as the conversation
progresses. The view turns each event into a Server-Sent Event for the browser.
It streams answer tokens as they arrive and surfaces every tool call, so the
operator can watch the agent reason over live cloud state.

The loop is a manual loop (not the SDK tool runner) for two reasons:
  1. Each tool must run with the Django ``request`` (the operator's token);
     a manual loop lets us inject it cleanly per call.
  2. We want fine-grained SSE events (token / tool_call / tool_result).
"""

import logging

from .client import (
    MAX_TOKENS,
    SYSTEM_PROMPT,
    get_client,
    get_effort,
    get_max_iterations,
    get_model,
)
from .tools import TOOL_SPECS, execute_tool

LOG = logging.getLogger(__name__)


def run_agent(request, messages):
    """Run the loop. ``messages`` is the API-format conversation so far.

    Yields dicts of shape:
      {"type": "token", "text": ...}
      {"type": "tool_call", "name": ..., "input": ...}
      {"type": "tool_result", "name": ..., "is_error": bool}
      {"type": "done"}
      {"type": "error", "message": ...}
    """
    try:
        client = get_client()
    except RuntimeError as exc:
        yield {"type": "error", "message": str(exc)}
        return

    model = get_model()
    effort = get_effort()
    convo = list(messages)

    for iteration in range(get_max_iterations()):
        try:
            with client.messages.stream(
                model=model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=TOOL_SPECS,
                thinking={"type": "adaptive"},
                output_config={"effort": effort},
                messages=convo,
            ) as stream:
                for text in stream.text_stream:
                    yield {"type": "token", "text": text}
                final = stream.get_final_message()
        except Exception as exc:  # noqa: BLE001
            LOG.exception("Claude request failed")
            yield {"type": "error", "message": "Claude request failed: %s" % exc}
            return

        # Preserve full content (text, thinking, tool_use blocks) for the next turn.
        convo.append({"role": "assistant", "content": final.content})

        if final.stop_reason != "tool_use":
            yield {"type": "done"}
            return

        tool_results = []
        for block in final.content:
            if block.type != "tool_use":
                continue
            yield {"type": "tool_call", "name": block.name, "input": block.input}
            result = execute_tool(request, block.name, block.input)
            entry = {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result["content"],
            }
            if result["is_error"]:
                entry["is_error"] = True
            tool_results.append(entry)
            yield {"type": "tool_result", "name": block.name,
                   "is_error": result["is_error"]}

        convo.append({"role": "user", "content": tool_results})

    # Exhausted the iteration budget without a natural end.
    yield {"type": "token",
           "text": "\n\n_(Reached the tool-call limit for this turn. "
                   "Ask a follow-up to continue.)_"}
    yield {"type": "done"}
