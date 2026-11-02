import assert from "node:assert/strict";
import test from "node:test";
import { PanelController } from "../../src/controller.ts";

const tick = () => new Promise((resolve) => setImmediate(resolve));
const deferred = () => {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
};
const state = (volume = 20, percent = 70, device = "speakers") => ({
  audio: { available: true, volume, muted: false, device_id: device, device_name: device, error: null },
  brightness: { available: true, percent, levels: [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100], instance_name: "panel", error: null },
  updated_at: new Date().toISOString(),
});
const backend = (overrides = {}) => ({
  getState: async () => state(), getCapabilities: async () => ({}), getDiagnostics: async () => ({}),
  setVolume: async (value) => state(value),
  setMute: async (muted) => ({ ...state(), audio: { ...state().audio, muted } }),
  setBrightness: async (value) => state(20, value),
  ...overrides,
});

test("mount only reads, and a read never overlaps another read", async () => {
  const read = deferred();
  let reads = 0;
  let writes = 0;
  const controller = new PanelController(backend({ getState: async () => { ++reads; return read.promise; }, setVolume: async () => { ++writes; return state(); } }), () => {});
  controller.start();
  controller.refresh();
  controller.refresh();
  assert.equal(reads, 1);
  assert.equal(writes, 0);
  read.resolve(state());
  await tick();
  controller.dispose();
});

test("a poll begun before a write cannot overwrite the confirmed value", async () => {
  const stale = deferred();
  let reads = 0;
  let model;
  const controller = new PanelController(backend({ getState: async () => ++reads === 1 ? state() : stale.promise }), (next) => { model = next; });
  controller.start();
  await tick();
  controller.refresh();
  controller.setVolume(65);
  controller.flushAudio();
  await tick();
  stale.resolve(state(5));
  await tick();
  assert.equal(model.state.audio.volume, 65);
  assert.equal(model.draftVolume, null);
  controller.dispose();
});

test("a poll begun during a write cannot replace its later confirmation", async () => {
  const write = deferred();
  const stale = deferred();
  let reads = 0;
  let model;
  const controller = new PanelController(backend({ getState: async () => ++reads === 1 ? state() : stale.promise, setVolume: async () => write.promise }), (next) => { model = next; });
  controller.start();
  await tick();
  controller.setVolume(65);
  controller.flushAudio();
  controller.refresh();
  write.resolve(state(65));
  await tick();
  stale.resolve(state(20));
  await tick();
  assert.equal(model.state.audio.volume, 65);
  controller.dispose();
});

test("device change drops pending writes and blocks the old pointer gesture", async () => {
  let current = state();
  const writes = [];
  const controller = new PanelController(backend({
    getState: async () => current,
    setVolume: async (value, target) => { writes.push([value, target]); return state(value, 70, target); },
  }), () => {});
  controller.start();
  await tick();
  controller.beginInteraction("volume");
  controller.setVolume(30);
  current = state(10, 70, "headphones");
  controller.refresh();
  await tick();
  controller.setVolume(40);
  controller.flushAudio();
  await tick();
  assert.deepEqual(writes, []);
  controller.endInteraction("volume");
  controller.setVolume(40);
  controller.flushAudio();
  await tick();
  assert.deepEqual(writes, [[40, "headphones"]]);
  controller.dispose();
});

test("pointer draft survives polling until the interaction ends", async () => {
  let model;
  const controller = new PanelController(backend(), (next) => { model = next; });
  controller.start();
  await tick();
  controller.beginInteraction("volume");
  controller.setVolume(35);
  controller.flushAudio();
  await tick();
  controller.refresh();
  await tick();
  assert.equal(model.draftVolume, 35);
  controller.endInteraction("volume");
  assert.equal(model.draftVolume, null);
  assert.equal(model.state.audio.volume, 35);
  controller.dispose();
});

test("brightness can complete while audio is waiting, without overwriting audio", async () => {
  const audio = deferred();
  let model;
  const controller = new PanelController(backend({ setVolume: async () => audio.promise }), (next) => { model = next; });
  controller.start();
  await tick();
  controller.setVolume(55);
  controller.flushAudio();
  controller.setBrightness(83);
  controller.flushBrightness();
  await tick();
  assert.equal(model.state.brightness.percent, 80);
  assert.equal(model.draftVolume, 55);
  audio.resolve(state(55, 70));
  await tick();
  assert.equal(model.state.audio.volume, 55);
  assert.equal(model.state.brightness.percent, 80);
  controller.dispose();
});

test("dispose ignores late responses and cancels unsent changes", async () => {
  const read = deferred();
  let notifications = 0;
  let writes = 0;
  const controller = new PanelController(backend({ getState: async () => read.promise, setVolume: async () => { ++writes; return state(); } }), () => { ++notifications; });
  controller.start();
  controller.dispose();
  read.resolve(state());
  await tick();
  assert.equal(notifications, 0);
  assert.equal(writes, 0);
});
