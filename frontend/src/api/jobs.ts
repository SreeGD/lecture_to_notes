import { apiFetch } from "./client";
import type {
  BrowseResponse,
  HealthResponse,
  JobCreateRequest,
  JobCreateResponse,
  JobDetail,
  JobOutputResponse,
  JobSummary,
  SearchResponse,
  TopicTaxonomyResponse,
} from "./types";

export const checkHealth = () => apiFetch<HealthResponse>("/health");

export const createJob = (data: JobCreateRequest) =>
  apiFetch<JobCreateResponse>("/jobs", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const listJobs = () => apiFetch<JobSummary[]>("/jobs");

export const getJob = (jobId: string) =>
  apiFetch<JobDetail>(`/jobs/${jobId}`);

export const getJobOutput = (jobId: string) =>
  apiFetch<JobOutputResponse>(`/jobs/${jobId}/output`);

export const cancelJob = (jobId: string) =>
  apiFetch<{ job_id: string; message: string }>(`/jobs/${jobId}/cancel`, {
    method: "POST",
  });

export const browseAudio = (path: string = "/") =>
  apiFetch<BrowseResponse>(`/browse?path=${encodeURIComponent(path)}`);

export const searchAudio = (query: string) =>
  apiFetch<SearchResponse>(`/browse/search?q=${encodeURIComponent(query)}`);

export const getTopics = () =>
  apiFetch<TopicTaxonomyResponse>("/browse/topics");
