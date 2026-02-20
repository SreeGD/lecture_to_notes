import { useState, useEffect } from "react";
import { getJobOutput } from "../api/jobs";
import type { JobOutputResponse } from "../api/types";

export function useJobOutput(jobId: string, isCompleted: boolean) {
  const [output, setOutput] = useState<JobOutputResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isCompleted) return;
    setLoading(true);
    getJobOutput(jobId)
      .then((data) => {
        setOutput(data);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed"))
      .finally(() => setLoading(false));
  }, [jobId, isCompleted]);

  return { output, loading, error };
}
