---
title: Writing an Agent Plugin
---

# Writing an Agent Plugin

An agent plugin is initialized with `(config, event_queue, stop_event)` and
implements `run()`. It collects events until `stop_event` is set. The plugin
places JSON-serializable dictionaries on `event_queue`. The shared sender sends
them to the indexer in batches.

```python
import time


class ExamplePlugin:
    def __init__(self, config, event_queue, stop_event):
        self.config = config
        self.event_queue = event_queue
        self.stop_event = stop_event

    def run(self):
        while not self.stop_event.is_set():
            self.event_queue.put({
                "event_type": "example",
                "data": {"value": 1},
                "timestamp": time.time(),
                "index": self.config.get("index", "default"),
                "host": self.config.get("host", "localhost"),
                "source": self.config.get("source", "example"),
                "sourcetype": self.config.get("sourcetype", "json"),
            })
            self.stop_event.wait(self.config.get("poll_interval", 5))
```

Add a dictionary under `AGENT["plugins"]` in the agent settings. By convention,
`name="example"` loads `agent.plugins.example_plugin:ExamplePlugin`. If the
module or class does not follow that convention, set an explicit `path`.

Common configuration includes `enabled`, `restart`, `poll_interval`, `index`,
`host`, `source`, `sourcetype`, and optional `db_alias`. Keep collection work
bounded, honor `stop_event`, and avoid placing non-JSON types on the queue.

When a plugin process exits, the agent restarts it after an exponential
backoff:

- `restart`: `True` (the default) restarts forever, `False` never restarts,
  and an integer caps consecutive restarts.
- `restart_backoff`: seconds before the first restart. The wait doubles on
  each consecutive restart. Default `1`.
- `restart_backoff_max`: the longest wait between restarts. Default `300`.
- `restart_reset_after`: seconds a process must stay up before its restart
  count resets to zero. Default `300`.

The agent checks plugins every 10 seconds, so the shortest real wait is about
10 seconds. A plugin may raise from `run()` when a source is unreachable at
startup; the backoff retries it until the source returns. The heartbeat
reports `plugins_alive` for each plugin, which excludes the sender process.

Test collection without a live indexer by supplying a multiprocessing-compatible
queue and stop event. Cover shutdown, inaccessible sources, rotation or cursor
behavior, serialization, and the absence of optional data. Never log agent
credentials or collected secrets.
