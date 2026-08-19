import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import test from "node:test";
import { buildSync } from "esbuild";
import vm from "node:vm";

const root = join(dirname(new URL(import.meta.url).pathname), "..");
const bundle = buildSync({
  entryPoints: [join(root, "src/agent_pack/dashboard/ui/flow.ts")],
  bundle: true,
  write: false,
  platform: "node",
  format: "cjs",
});
const context = vm.createContext({ module: { exports: {} }, exports: {} });
vm.runInContext(bundle.outputFiles[0].text, context);
const { planPhase, flowNodes, flowProgress } = context.module.exports;

function runWithPlan(plan, steps) {
  return {
    invocation_id: "test-id",
    profile_id: "generic-agent",
    plan,
    steps,
    outcome: "open",
    started_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    request_text: "demo",
    events: [{ event: "started", started_at: "2026-01-01T00:00:00Z", request_text: "demo" }],
  };
}

test("planPhase marks next step upcoming when one is active", () => {
  const run = runWithPlan(["product", "designer", "qa"], [
    { name: "product", status: "done", log: [] },
    { name: "designer", status: "started", log: [] },
  ]);
  const byName = Object.fromEntries(run.steps.map((step) => [step.name, step]));
  const activeIndex = run.plan.findIndex((label) => byName[label]?.status === "started");
  const nextIndex = run.plan.findIndex((label) => byName[label]?.status !== "done");
  assert.equal(planPhase("product", 0, activeIndex, nextIndex, byName), "done");
  assert.equal(planPhase("designer", 1, activeIndex, nextIndex, byName), "active");
  assert.equal(planPhase("qa", 2, activeIndex, nextIndex, byName), "upcoming");
});

test("flowNodes includes planned steps before any step events", () => {
  const run = runWithPlan(["product", "designer"], []);
  const nodes = flowNodes(run);
  assert.equal(nodes.length, 4);
  assert.equal(nodes[1].phase, "upcoming");
  assert.equal(nodes[2].phase, "waiting");
});

test("flowProgress counts done plan steps only", () => {
  const run = runWithPlan(
    ["product", "designer", "qa"],
    [{ name: "product", status: "done", log: [] }],
  );
  assert.equal(flowProgress(run).label, "1/3");
});

test("flowNodes appends unplanned extra step", () => {
  const run = runWithPlan(["product"], [{ name: "hotfix", status: "started", log: [] }]);
  const names = flowNodes(run).map((node) => node.name);
  assert.equal(names.join(","), "start,product,hotfix,complete");
});
