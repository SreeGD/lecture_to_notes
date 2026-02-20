import { useState, useEffect, useCallback, useRef } from "react";
import { listJobs } from "../api/jobs";
import type { JobSummary } from "../api/types";

export function useJobs() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const jobsRef = useRef(jobs);
  jobsRef.current = jobs;

  const refresh = useCallback(async () => {
    try {
      const data = await listJobs();
      setJobs(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch jobs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(() => {
      const hasActive = jobsRef.current.some(
        (j) => j.status === "queued" || j.status === "running",
      );
      if (hasActive) refresh();
    }, 3000);
    return () => clearInterval(id);
  }, [refresh]);

  return { jobs, loading, error, refresh };
}
