import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useJobDetail } from "../hooks/useJobDetail";
import { useJobOutput } from "../hooks/useJobOutput";
import { cancelJob } from "../api/jobs";
import { StatusBadge } from "../components/StatusBadge";
import { StepProgress } from "../components/StepProgress";
import { ErrorDisplay } from "../components/ErrorDisplay";
import { OutputViewer } from "../components/OutputViewer";
import { timeAgo, formatDuration } from "../utils";

export function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const { job, loading, error } = useJobDetail(jobId!);
  const { output, loading: outputLoading } = useJobOutput(
    jobId!,
    job?.status === "completed",
  );
  const navigate = useNavigate();
  const [cancelling, setCancelling] = useState(false);

  const handleCancel = async () => {
    if (!jobId || cancelling) return;
    setCancelling(true);
    try {
      await cancelJob(jobId);
    } catch {
      setCancelling(false);
    }
  };

  if (loading) {
    return <p className="py-8 text-center text-sm text-gray-500">Loading...</p>;
  }

  if (error || !job) {
    return <ErrorDisplay message={error || "Job not found"} />;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link
          to="/"
          className="text-sm text-blue-600 hover:text-blue-800 no-underline"
        >
          &larr; Back to dashboard
        </Link>
        <div className="mt-2 flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{job.title}</h1>
            <p className="mt-0.5 text-sm text-gray-500">
              ID: {job.job_id} &middot; Created {timeAgo(job.created_at)}
              {job.elapsed_seconds != null && job.elapsed_seconds > 0 && (
                <> &middot; Elapsed: {formatDuration(job.elapsed_seconds)}</>
              )}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {(job.status === "queued" || job.status === "running") && (
              <button
                onClick={handleCancel}
                disabled={cancelling}
                className="rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {cancelling ? "Stopping..." : "Stop Job"}
              </button>
            )}
            {(job.status === "completed" || job.status === "failed") && (
              <button
                onClick={() =>
                  navigate("/", {
                    state: {
                      resubmit: {
                        urls: job.urls,
                        title: job.title,
                        config: job.config,
                      },
                    },
                  })
                }
                className="rounded-md border border-blue-300 bg-white px-3 py-1.5 text-sm font-medium text-blue-600 hover:bg-blue-50"
              >
                Resubmit
              </button>
            )}
            <StatusBadge status={job.status} />
          </div>
        </div>
      </div>

      {/* Pipeline progress */}
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-700">
            Pipeline Progress
          </h3>
          {job.step_detail && (job.status === "running" || job.status === "queued") && (
            <span className="text-sm text-blue-600 animate-pulse">
              {job.step_detail}
            </span>
          )}
        </div>
        <StepProgress
          currentStep={job.current_step}
          failed={job.status === "failed"}
        />
      </div>

      {/* Progress log */}
      {job.progress_log.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-6">
          <h3 className="mb-3 text-sm font-medium text-gray-700">
            Activity Log
          </h3>
          <div className="space-y-2">
            {job.progress_log.map((entry, i) => (
              <div key={i} className="flex items-start gap-3 text-sm">
                <span className="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full bg-blue-400" />
                <div className="min-w-0 flex-1">
                  <span className="text-gray-700">{entry.message}</span>
                </div>
                <span className="flex-shrink-0 text-xs text-gray-400 whitespace-nowrap">
                  {new Date(entry.timestamp).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* URLs */}
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <h3 className="mb-3 text-sm font-medium text-gray-700">
          Source URLs ({job.urls.length})
        </h3>
        <ul className="space-y-2">
          {job.url_progress.map((up) => (
            <li
              key={up.url}
              className="flex items-center justify-between text-sm"
            >
              <span className="min-w-0 truncate text-gray-600">{up.url}</span>
              <span
                className={`ml-2 text-xs ${
                  up.status === "completed"
                    ? "text-green-600"
                    : up.error
                      ? "text-red-600"
                      : "text-gray-400"
                }`}
              >
                {up.error || up.status}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {/* Timestamps */}
      <div className="flex flex-wrap gap-6 text-sm text-gray-500">
        {job.started_at && (
          <span>Started: {new Date(job.started_at).toLocaleString()}</span>
        )}
        {job.completed_at && (
          <span>Completed: {new Date(job.completed_at).toLocaleString()}</span>
        )}
        {job.elapsed_seconds != null && job.completed_at && (
          <span>Duration: {formatDuration(job.elapsed_seconds)}</span>
        )}
      </div>

      {/* Error */}
      {job.status === "failed" && job.error && (
        <ErrorDisplay message={job.error} />
      )}

      {/* Output */}
      {job.status === "completed" && (
        <div>
          <h2 className="mb-4 text-lg font-semibold text-gray-900">Output</h2>
          {outputLoading ? (
            <p className="text-sm text-gray-500">Loading output...</p>
          ) : output ? (
            <OutputViewer
              jobId={job.job_id}
              output={output}
              outputFiles={job.output_files}
            />
          ) : null}
        </div>
      )}
    </div>
  );
}
