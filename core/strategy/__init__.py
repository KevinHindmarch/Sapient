"""Trading strategy pieces that never talk to a broker: market calendar, exit/entry
rules, share sizing and the scan scheduler. Everything here only produces
proposals; orders still go through core.execution_safety.IntentService."""
