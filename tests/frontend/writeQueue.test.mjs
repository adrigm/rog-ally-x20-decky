import assert from "node:assert/strict";
import test from "node:test";
import { WriteQueue } from "../../src/writeQueue.ts";

const tick = () => new Promise((resolve) => setImmediate(resolve));
const pause = (ms = 15) => new Promise((resolve) => setTimeout(resolve, ms));
const deferred = () => {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
};

test("coalesces slider values while preserving a separate mute request", async () => {
  const calls = [];
  const queue = new WriteQueue(async (write) => { calls.push(write); }, 0);
  queue.push({ kind: "volume", target: "A", value: 10 });
  queue.push({ kind: "volume", target: "A", value: 40 });
  queue.push({ kind: "mute", target: "A", value: true });
  queue.flush();
  await pause();
  assert.deepEqual(calls.map(({ kind, value }) => [kind, value]), [["volume", 40], ["mute", true]]);
  queue.dispose();
});

test("never overlaps writes and sends the last value received during a request", async () => {
  const first = deferred();
  const calls = [];
  const queue = new WriteQueue(async (write) => {
    calls.push(write.value);
    if (calls.length === 1) await first.promise;
  }, 0);
  queue.push({ kind: "volume", target: "A", value: 10 });
  queue.flush();
  queue.push({ kind: "volume", target: "A", value: 20 });
  queue.push({ kind: "volume", target: "A", value: 30 });
  queue.flush();
  await tick();
  assert.deepEqual(calls, [10]);
  first.resolve();
  await pause();
  assert.deepEqual(calls, [10, 30]);
  queue.dispose();
});

test("dispose prevents queued writes from resuming after an in-flight call", async () => {
  const first = deferred();
  const calls = [];
  const queue = new WriteQueue(async (write) => { calls.push(write.value); await first.promise; }, 0);
  queue.push({ kind: "brightness", target: "panel", value: 30 });
  queue.flush();
  queue.push({ kind: "brightness", target: "panel", value: 90 });
  queue.dispose();
  first.resolve();
  await pause();
  assert.deepEqual(calls, [30]);
});

test("a rejected operation does not block later requests", async () => {
  const calls = [];
  const queue = new WriteQueue(async (write) => { calls.push(write.kind); if (write.kind === "volume") throw new Error("unavailable"); }, 0);
  queue.push({ kind: "volume", target: "A", value: 30 });
  queue.push({ kind: "mute", target: "A", value: true });
  queue.flush();
  await pause();
  assert.deepEqual(calls, ["volume", "mute"]);
  queue.dispose();
});
