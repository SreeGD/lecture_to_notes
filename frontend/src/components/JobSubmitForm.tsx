import { useState, useEffect, type FormEvent } from "react";
import { createJob } from "../api/jobs";
import { AudioBrowser } from "./AudioBrowser";

export interface JobFormValues {
  urls?: string[];
  title?: string;
  speaker?: string;
  whisper_model?: string;
  whisper_backend?: string;
  enable_diarization?: boolean;
  enable_llm?: boolean;
  generate_pdf?: boolean;
  vad_filter?: boolean;
  prompt?: string;
}

interface Props {
  onSubmitted: () => void;
  initialValues?: JobFormValues;
}

export function JobSubmitForm({ onSubmitted, initialValues }: Props) {
  const [urls, setUrls] = useState("");
  const [title, setTitle] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [speaker, setSpeaker] = useState("");
  const [whisperModel, setWhisperModel] = useState("large-v3");
  const [enableDiarization, setEnableDiarization] = useState(false);
  const [enableLlm, setEnableLlm] = useState(true);
  const [generatePdf, setGeneratePdf] = useState(false);
  const [vadFilter, setVadFilter] = useState(true);
  const [prompt, setPrompt] = useState("");
  const [enrichmentMode, setEnrichmentMode] = useState("auto");
  const [whisperBackend, setWhisperBackend] = useState("faster-whisper");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showBrowser, setShowBrowser] = useState(false);

  useEffect(() => {
    if (!initialValues) return;
    if (initialValues.urls) setUrls(initialValues.urls.join("\n"));
    if (initialValues.title) setTitle(initialValues.title);
    if (initialValues.speaker) setSpeaker(initialValues.speaker);
    if (initialValues.whisper_model) setWhisperModel(initialValues.whisper_model);
    if (initialValues.whisper_backend) setWhisperBackend(initialValues.whisper_backend);
    if (initialValues.enable_diarization !== undefined) setEnableDiarization(initialValues.enable_diarization);
    if (initialValues.enable_llm !== undefined) setEnableLlm(initialValues.enable_llm);
    if (initialValues.generate_pdf !== undefined) setGeneratePdf(initialValues.generate_pdf);
    if (initialValues.vad_filter !== undefined) setVadFilter(initialValues.vad_filter);
    if (initialValues.prompt) setPrompt(initialValues.prompt);
    // Show advanced options if any non-default values are set
    if (
      initialValues.speaker ||
      (initialValues.whisper_model && initialValues.whisper_model !== "large-v3") ||
      (initialValues.whisper_backend && initialValues.whisper_backend !== "faster-whisper") ||
      initialValues.enable_diarization
    ) {
      setShowAdvanced(true);
    }
    setSuccess(null);
    setError(null);
  }, [initialValues]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const parsedUrls = urls
      .split(/[\n,]+/)
      .map((u) => u.trim())
      .filter(Boolean);

    if (parsedUrls.length === 0) {
      setError("Please enter at least one URL.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      const resp = await createJob({
        urls: parsedUrls,
        title: title || undefined,
        speaker: speaker || undefined,
        whisper_model: whisperModel,
        enable_diarization: enableDiarization,
        enable_llm: enableLlm,
        generate_pdf: generatePdf,
        vad_filter: vadFilter,
        whisper_backend: whisperBackend,
        prompt: prompt || undefined,
        enrichment_mode: enrichmentMode,
      });
      setSuccess(`Job ${resp.job_id} submitted.`);
      setUrls("");
      setTitle("");
      onSubmitted();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Submission failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm"
    >
      <h2 className="mb-4 text-lg font-semibold text-gray-900">
        Submit New Job
      </h2>

      <div className="mb-4">
        <label className="mb-1 block text-sm font-medium text-gray-700">
          Audio URLs (one per line)
        </label>
        <textarea
          value={urls}
          onChange={(e) => setUrls(e.target.value)}
          rows={3}
          placeholder="https://example.com/lecture.mp3"
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
        />
        <button
          type="button"
          onClick={() => setShowBrowser(true)}
          className="mt-1 text-sm text-blue-600 hover:text-blue-800"
        >
          Browse ISKCON Desire Tree Audio
        </button>
      </div>

      <div className="mb-4">
        <label className="mb-1 block text-sm font-medium text-gray-700">
          Title
        </label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Lecture Notes"
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
        />
      </div>

      <div className="mb-4">
        <label className="mb-1 block text-sm font-medium text-gray-700">
          Prompt (optional)
        </label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          placeholder="Custom instructions for LLM enrichment, e.g. 'Focus on the practical applications discussed' or 'Include detailed Sanskrit word analysis'"
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
        />
      </div>

      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="mb-3 text-sm text-blue-600 hover:text-blue-800"
      >
        {showAdvanced ? "\u25BE" : "\u25B8"} Advanced Options
      </button>

      {showAdvanced && (
        <div className="mb-4 space-y-3 rounded-md bg-gray-50 p-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Speaker
            </label>
            <input
              type="text"
              value={speaker}
              onChange={(e) => setSpeaker(e.target.value)}
              placeholder="Speaker name"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Whisper Model
            </label>
            <select
              value={whisperModel}
              onChange={(e) => setWhisperModel(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
            >
              <option value="tiny">tiny</option>
              <option value="base">base</option>
              <option value="small">small</option>
              <option value="medium">medium</option>
              <option value="large-v3">large-v3</option>
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Whisper Backend
            </label>
            <select
              value={whisperBackend}
              onChange={(e) => setWhisperBackend(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
            >
              <option value="faster-whisper">faster-whisper (CPU)</option>
              <option value="whisper.cpp">whisper.cpp (Metal/CoreML)</option>
            </select>
          </div>

          <div className="flex flex-wrap gap-6">
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={enableDiarization}
                onChange={(e) => setEnableDiarization(e.target.checked)}
                className="rounded"
              />
              Speaker Diarization
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={enableLlm}
                onChange={(e) => setEnableLlm(e.target.checked)}
                className="rounded"
              />
              LLM Enrichment
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={generatePdf}
                onChange={(e) => setGeneratePdf(e.target.checked)}
                className="rounded"
              />
              Generate PDF
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={vadFilter}
                onChange={(e) => setVadFilter(e.target.checked)}
                className="rounded"
              />
              VAD Filter
            </label>
          </div>

          {enableLlm && (
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Enrichment Mode
              </label>
              <select
                value={enrichmentMode}
                onChange={(e) => setEnrichmentMode(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
              >
                <option value="auto">Auto (recommended)</option>
                <option value="lecture-centric">Lecture-centric — thematic notes, stories &amp; analogies</option>
                <option value="verse-centric">Verse-centric — detailed per-verse 15-section analysis</option>
              </select>
              <p className="mt-1 text-xs text-gray-500">
                Auto selects lecture-centric when few verse references are detected.
              </p>
            </div>
          )}
        </div>
      )}

      {error && (
        <p className="mb-3 text-sm text-red-600">{error}</p>
      )}
      {success && (
        <p className="mb-3 text-sm text-green-600">{success}</p>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {submitting ? "Submitting..." : "Submit Job"}
      </button>

      {showBrowser && (
        <AudioBrowser
          onClose={() => setShowBrowser(false)}
          onAdd={(newUrls) => {
            setUrls((prev) => {
              const trimmed = prev.trim();
              return trimmed
                ? trimmed + "\n" + newUrls.join("\n")
                : newUrls.join("\n");
            });
          }}
        />
      )}
    </form>
  );
}
