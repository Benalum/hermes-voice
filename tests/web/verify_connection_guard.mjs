import assert from "node:assert/strict";

import {
  ConnectionGuard,
  guardConnectionCallback,
} from "../../hermes_voice/web/connection_guard.mjs";

const guard = new ConnectionGuard();
const firstSocket = { name: "first" };
const secondSocket = { name: "second" };
const first = guard.activate(firstSocket);
const calls = [];
const firstHandler = guardConnectionCallback(
  guard,
  first,
  (value) => {
    calls.push(value);
    return "handled";
  },
);

assert.equal(firstHandler("first-event"), "handled");
assert.deepEqual(calls, ["first-event"]);
assert.equal(guard.current, first);

const second = guard.activate(secondSocket);
assert.equal(guard.isCurrent(first), false);
assert.equal(guard.isCurrent(second), true);
assert.equal(firstHandler("stale-event"), undefined);
assert.deepEqual(calls, ["first-event"]);

assert.equal(guard.invalidate(first), false);
assert.equal(guard.current, second);

const secondHandler = guardConnectionCallback(
  guard,
  second,
  (value) => calls.push(value),
);
secondHandler("second-event");
assert.deepEqual(calls, ["first-event", "second-event"]);

assert.equal(guard.invalidate(second), true);
assert.equal(guard.current, null);
secondHandler("closed-event");
assert.deepEqual(calls, ["first-event", "second-event"]);
