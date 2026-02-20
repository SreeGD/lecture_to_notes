import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useJobs } from "../hooks/useJobs";
import { JobSubmitForm, type JobFormValues } from "../components/JobSubmitForm";
import { JobList } from "../components/JobList";
import { ErrorDisplay } from "../components/ErrorDisplay";

interface ResubmitState {
  urls: string[];
  title: string;
  config: Record<string, unknown>;
}

export function DashboardPage() {
  const { jobs, loading, error, refresh } = useJobs();
  const location = useLocation();
  const navigate = useNavigate();
  const [initialValues, setInitialValues] = useState<
    JobFormValues | undefined
  >();

  useEffect(() => {
    const resubmit = (location.state as { resubmit?: ResubmitState } | null)
      ?.resubmit;
    if (resubmit) {
      setInitialValues({
        urls: resubmit.urls,
        title: resubmit.title,
        speaker: resubmit.config.speaker as string | undefined,
        whisper_model: resubmit.config.whisper_model as string | undefined,
        whisper_backend: resubmit.config.whisper_backend as string | undefined,
        enable_diarization: resubmit.config.enable_diarization as
          | boolean
          | undefined,
        enable_llm: resubmit.config.enable_llm as boolean | undefined,
        generate_pdf: resubmit.config.generate_pdf as boolean | undefined,
        vad_filter: resubmit.config.vad_filter as boolean | undefined,
        prompt: resubmit.config.prompt as string | undefined,
      });
      // Clear router state so it doesn't persist on refresh
      navigate("/", { replace: true, state: {} });
    }
  }, [location.state, navigate]);

  return (
    <div className="space-y-8">
      <JobSubmitForm onSubmitted={refresh} initialValues={initialValues} />

      <div>
        <h2 className="mb-4 text-lg font-semibold text-gray-900">Jobs</h2>
        {error && <ErrorDisplay message={error} />}
        <JobList jobs={jobs} loading={loading} />
      </div>
    </div>
  );
}
