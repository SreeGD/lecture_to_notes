import { useState, useEffect, useCallback } from "react";
import { getJob } from "../api/jobs";
import type { JobDetail } from "../api/types";

export function useJobDetail(jobId: string) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await getJob(jobId);
      setJob(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch job");
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!job) return;
    const isActive = job.status === "queued" || job.status === "running";
    if (!isActive) return;
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, [job?.status, refresh]);

  return { job, loading, error, refresh };
}
