import { renderUpgradeBanner } from "./views";
import type { Snapshot, UpgradeStatus } from "./types";

export type UpgradeContext = {
  view: string;
  getData: () => Snapshot | null;
  paint: () => void;
  reloadSnapshot: () => Promise<void>;
  resetFingerprint: () => void;
};

const upgrade = {
  status: null as UpgradeStatus | null,
  busy: false,
};

export function upgradeBanner(ctx: UpgradeContext): string {
  if (ctx.view !== "overview") {
    return "";
  }
  return renderUpgradeBanner(upgrade.status, upgrade.busy);
}

function repaintOverview(ctx: UpgradeContext): void {
  if (ctx.view === "overview" && ctx.getData()) {
    ctx.paint();
  }
}

export async function loadUpgradeStatus(ctx: UpgradeContext, force = false): Promise<void> {
  try {
    const url = force ? "/api/upgrade-status?force=1" : "/api/upgrade-status";
    const resp = await fetch(url);
    if (!resp.ok) {
      throw new Error("upgrade status failed");
    }
    upgrade.status = (await resp.json()) as UpgradeStatus | null;
    repaintOverview(ctx);
  } catch {
    upgrade.status = {
      available: false,
      current_tag: "",
      latest_tag: "",
      tag_moved: false,
      error: "Could not check for updates.",
    };
    repaintOverview(ctx);
  }
}

export async function runUpgrade(ctx: UpgradeContext): Promise<void> {
  if (upgrade.busy || !upgrade.status?.available) {
    return;
  }
  upgrade.busy = true;
  repaintOverview(ctx);
  const prior = upgrade.status;
  try {
    const resp = await fetch("/api/upgrade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tag: prior.latest_tag }),
    });
    if (!resp.ok) {
      const payload = (await resp.json()) as { error?: string };
      throw new Error(payload.error || "upgrade failed");
    }
    ctx.resetFingerprint();
    await ctx.reloadSnapshot();
    await loadUpgradeStatus(ctx, true);
  } catch (err) {
    const message = err instanceof Error ? err.message : "upgrade failed";
    upgrade.status = {
      available: prior.available,
      current_tag: prior.current_tag,
      latest_tag: prior.latest_tag,
      tag_moved: prior.tag_moved,
      error: message,
    };
    repaintOverview(ctx);
  } finally {
    upgrade.busy = false;
    repaintOverview(ctx);
  }
}

export function handleUpgradeClick(target: HTMLElement, ctx: UpgradeContext): boolean {
  if (target.closest("[data-upgrade-check]")) {
    void loadUpgradeStatus(ctx, true);
    return true;
  }
  if (target.closest("[data-upgrade-run]") && !upgrade.busy) {
    void runUpgrade(ctx);
    return true;
  }
  return false;
}

export function bootUpgrade(ctx: UpgradeContext): void {
  void loadUpgradeStatus(ctx);
}
