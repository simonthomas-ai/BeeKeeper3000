# Camera outbox: persistent detection suppression

The camera outbox stores detection cooldowns in SQLite alongside pending metadata
events. A station restart therefore does not immediately emit another event for
the same species and prey-detected state.

## Transaction contract

- Event insertion and cooldown advancement occur in one SQLite BEGIN IMMEDIATE
  transaction.
- A recent matching detection is suppressed using a wall-clock epoch timestamp.
- The cooldown advances only when the event row is successfully inserted.
- If the outbox is full, the transaction rolls back; after space is freed, the
  event can be inserted without waiting through a false cooldown.
- Pending event data remains metadata-only. The cooldown table stores only a
  species label, boolean prey state and timestamp.
- A backwards system-clock adjustment fails closed by keeping the cooldown
  active rather than creating a burst of duplicate observations.

The default 30-second interval is an operational duplicate-suppression setting,
not a biological observation window. Operators may change it for their camera
geometry and capture rate. It does not merge or delete previously accepted events.

## Migration and backup

The detection_cooldowns table is created automatically for existing outbox
databases. No queued events are rewritten or removed. Include the camera outbox
SQLite database in a station backup and restore drill before deployment; the
base station backup currently documents other stores separately.

## Validation boundary

Unit tests verify cooldown persistence across object/runtime restarts, expiry,
and transactional behavior when capacity is exhausted. These are synthetic
software tests. They do not establish species-detection quality or acceptance
on a physical camera.
