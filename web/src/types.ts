export interface Passage {
  number: number;
  document_id: string;
  title: string;
  start: number;
  end: number;
  text: string;
  score?: number;
}

export interface Part {
  display: string;
  name: string;
  model: string | null;
}

export interface ConfigurationDescription {
  key: string;
  display: string;
  chunker: Part;
  embedder: Part | null;
  search_mode: string;
  reranker: Part | null;
  generator: Part | null;
  top_k: number;
  candidates: number;
}

export interface Selection {
  chunker: string;
  embedder: string | null;
  search_mode: string;
  reranker: string | null;
  generator: string | null;
  top_k: number;
  candidates: number;
}

export interface CatalogOption {
  id: string;
  label: string;
  model: string | null;
  expensive: boolean;
}

export interface Catalog {
  chunkers: CatalogOption[];
  embedders: CatalogOption[];
  search_modes: string[];
  rerankers: CatalogOption[];
  generators: CatalogOption[];
  initial: Selection;
}

export interface Job {
  id: number;
  kind: string;
  title: string;
  status: "queued" | "running" | "done" | "failed";
  done: number;
  total: number;
  message: string;
  error: string;
  result: Record<string, unknown>;
  created_at: string;
  finished_at: string | null;
}

export interface User {
  id: number;
  email: string;
  role: "admin" | "user";
}

export interface PrescriptionItem {
  outcome: string;
  label: string;
  count: number;
  share: number;
  stage: string;
  candidates: string[];
  same_plan_as: string | null;
  notes?: string[];
  plan: {
    focus: string;
    description: string;
    chunkers: string[];
    embedders: string[];
    search_modes: string[];
    rerankers: string[];
    generators: string[];
    context_k: number;
  } | null;
}

export interface ExaminationSummary {
  total: number;
  evaluated: number;
  errors: number;
  counts: Record<string, number>;
  labels: Record<string, string>;
  correct_rate: number | null;
  correct_low: number | null;
  correct_high: number | null;
  failures: [string, number][];
  cost_usd: number;
  paid_usd: number;
  judge_cost_usd: number;
  prescription: PrescriptionItem[];
}

export interface Examination {
  id: number;
  label: string;
  target_kind: "own" | "external";
  target: Record<string, unknown> & { display?: string; name?: string; url?: string };
  configuration_id: number | null;
  external_system_id: number | null;
  questions: number;
  baseline_id: number | null;
  created_at: string;
  job: Job | null;
  summary: ExaminationSummary | Record<string, never>;
}

export interface CaseBrief {
  id: number;
  question_id: string;
  question: string;
  source: string;
  outcome: string;
  wrong_gold: boolean;
  scores: { correctness: number; faithfulness: number; citation: number } | null;
  context_gold_rank: number | null;
  candidate_gold_rank: number | null;
  error: string | null;
}

export interface ExperimentRow {
  config_key: string;
  configuration: string;
  retrieval: string;
  generator: string;
  questions: number;
  correctness: number;
  correctness_low: number;
  correctness_high: number;
  faithfulness: number;
  citation: number;
  gold_in_context: number;
  cost_per_1k_answers_usd: number;
  latency_p50_s: number;
  tied_with_best: boolean;
  gap_to_best: number;
  spec: Record<string, unknown> | null;
  gain?: number | null;
  gain_low?: number | null;
  gain_high?: number | null;
  gain_significant?: boolean;
}

export interface Baseline {
  examination_id: number;
  configuration: string;
  correctness: number;
  correctness_low: number;
  correctness_high: number;
  questions: number;
}

export interface Experiment {
  id: number;
  name: string;
  purpose: string;
  config: Record<string, unknown>;
  run_id: string;
  examination_id: number | null;
  created_at: string;
  job: Job | null;
  summary: {
    run_id?: string;
    questions?: number;
    primary_metric?: string;
    answers?: ExperimentRow[];
    retrieval?: Record<string, number | string | null>[];
    recommendation?: { config_key: string; display: string; reason: string; spec: Record<string, unknown> | null } | null;
    baseline?: Baseline | null;
    paid_usd?: number;
    failed?: number;
  };
}
