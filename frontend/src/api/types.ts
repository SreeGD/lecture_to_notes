export type JobStatus = "queued" | "running" | "completed" | "failed";

export type PipelineStep =
  | "pending"
  | "downloading"
  | "transcribing"
  | "enriching"
  | "validating"
  | "compiling"
  | "pdf_generating"
  | "completed"
  | "failed";

export interface JobCreateRequest {
  urls: string[];
  title?: string;
  speaker?: string;
  whisper_model?: string;
  enable_diarization?: boolean;
  enable_llm?: boolean;
  generate_pdf?: boolean;
  vad_filter?: boolean;
  whisper_backend?: string;
  prompt?: string;
  enrichment_mode?: string;
  output_dir?: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  active_jobs: number;
}

export interface JobCreateResponse {
  job_id: string;
  status: JobStatus;
  message: string;
}

export interface ProgressLogEntry {
  timestamp: string;
  step: string;
  message: string;
}

export interface URLProgress {
  url: string;
  order: number;
  status: string;
  error: string | null;
}

export interface JobSummary {
  job_id: string;
  status: JobStatus;
  current_step: PipelineStep;
  step_detail: string;
  title: string;
  url_count: number;
  created_at: string;
  completed_at: string | null;
  elapsed_seconds: number | null;
  error: string | null;
}

export interface JobDetail {
  job_id: string;
  status: JobStatus;
  current_step: PipelineStep;
  step_detail: string;
  title: string;
  urls: string[];
  url_progress: URLProgress[];
  progress_log: ProgressLogEntry[];
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  elapsed_seconds: number | null;
  error: string | null;
  output_dir: string | null;
  output_files: string[];
  config: Record<string, unknown>;
}

export interface Chapter {
  number: number;
  title: string;
  content_markdown: string;
  verse_references: string[];
  themes: string[];
}

export interface CompilationReport {
  total_chapters: number;
  total_words: number;
  total_verses_referenced?: number;
  total_glossary_entries?: number;
  verified_verse_count?: number;
  unverified_verse_count?: number;
}

export interface BookOutput {
  title: string;
  subtitle: string | null;
  speaker: string | null;
  chapters: Chapter[];
  full_book_markdown: string;
  report: CompilationReport;
  summary: string;
}

export interface PDFOutput {
  pdf_path: string;
  title: string;
  total_pages: number;
  file_size_kb: number;
  summary: string;
}

export interface JobOutputResponse {
  job_id: string;
  book: BookOutput;
  pdf: PDFOutput | null;
}

export interface BrowseEntry {
  name: string;
  href: string;
  is_dir: boolean;
  size: string | null;
  modified: string | null;
}

export interface BrowseResponse {
  path: string;
  parent: string | null;
  entries: BrowseEntry[];
}

export interface SearchEntry {
  name: string;
  href: string;
  is_dir: boolean;
  size: string | null;
  breadcrumb: string;
}

export interface SearchGroup {
  group_title: string;
  entries: SearchEntry[];
}

export interface SearchResponse {
  query: string;
  total: number;
  groups: SearchGroup[];
}

export interface TopicEntry {
  slug: string;
  label: string;
  search_terms: string[];
  category: string;
}

export interface TopicCategory {
  category: string;
  label: string;
  topics: TopicEntry[];
}

export interface TopicTaxonomyResponse {
  categories: TopicCategory[];
}
