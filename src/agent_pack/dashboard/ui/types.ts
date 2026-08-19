export type StepLogEntry = {
  status: string;
  at: string;
  detail: string;
};

export type Step = {
  name: string;
  status: string;
  at?: string;
  detail?: string;
  log?: StepLogEntry[];
};

export type RunEvent = {
  event?: string;
  started_at?: string;
  completed_at?: string;
  request_text?: string;
  outcome?: string;
  name?: string;
  status?: string;
  at?: string;
  detail?: string;
};

export type Run = {
  invocation_id: string;
  profile_id: string;
  request_text: string;
  started_at: string;
  completed_at: string | null;
  outcome: string;
  plan?: string[];
  steps?: Step[];
  events?: RunEvent[];
  pack_name?: string | null;
  pack_tag?: string | null;
  pack_commit?: string | null;
};

export type Skill = {
  id: string;
  name: string;
  description: string;
  path: string;
  body?: string;
};

export type Profile = {
  id: string;
  name: string;
  description: string;
  plan?: string[];
  path: string;
  body?: string;
};

export type UpgradeStatus = {
  available: boolean;
  current_tag: string;
  latest_tag: string;
  tag_moved: boolean;
  error?: string;
};

export type Snapshot = {
  kind: string;
  root: string;
  name: string;
  pack: { name?: string; description?: string; valid?: boolean; errors: string[] } | null;
  lock: {
    name: string;
    source: string;
    tag: string;
    commit: string;
    state: string;
  } | null;
  constitution: string;
  skills: Skill[];
  profiles: Profile[];
  projections: { path: string; source: string; present: boolean }[];
  runs: Run[];
  counts: Record<string, number>;
};

export type FlowNode = {
  kind: "start" | "complete" | "step";
  name: string;
  label: string;
  phase: string;
  status: string;
  at: string;
  detail: string;
  log: StepLogEntry[];
};

export type TimelineRow = {
  at: string;
  kind: string;
  runId: string;
  profile: string;
  detail: string;
};

export type ChipFn = (label: string, tone: string) => string;
export type EscapeFn = (value: unknown) => string;
