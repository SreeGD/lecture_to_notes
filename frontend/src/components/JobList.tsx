import type { JobSummary } from "../api/types";
import { JobCard } from "./JobCard";

export function JobList({ jobs, loading }: { jobs: JobSummary[]; loading: boolean }) {
  if (loading) {
    return <p className="py-8 text-center text-sm text-gray-500">Loading jobs...</p>;
  }

  if (jobs.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-gray-500">
        No jobs yet. Submit one above to get started.
      </p>
    );
  }

  const sorted = [...jobs].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  return (
    <div className="space-y-2">
      {sorted.map((job) => (
        <JobCard key={job.job_id} job={job} />
      ))}
    </div>
  );
}
