import { Link } from "react-router-dom";
import type { JobSummary } from "../api/types";
import { StatusBadge } from "./StatusBadge";
import { timeAgo, formatDuration } from "../utils";

export function JobCard({ job }: { job: JobSummary }) {
  return (
    <Link
      to={`/jobs/${job.job_id}`}
      className="block no-underline"
    >
      <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-5 py-4 transition hover:border-blue-300 hover:shadow-sm">
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium text-gray-900">{job.title}</p>
          <p className="mt-0.5 text-xs text-gray-500">
            {job.url_count} URL{job.url_count !== 1 ? "s" : ""} &middot;{" "}
            {job.step_detail || (job.current_step !== "pending" ? job.current_step : "waiting")}
          </p>
        </div>
        <div className="ml-4 flex items-center gap-4">
          <StatusBadge status={job.status} />
          <div className="text-right">
            <span className="block text-xs text-gray-400 whitespace-nowrap">
              {timeAgo(job.created_at)}
            </span>
            {job.elapsed_seconds != null && job.elapsed_seconds > 0 && (
              <span className="block text-xs text-gray-400 whitespace-nowrap">
                {formatDuration(job.elapsed_seconds)}
              </span>
            )}
          </div>
        </div>
      </div>
    </Link>
  );
}
