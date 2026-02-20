import Markdown from "react-markdown";
import type { JobOutputResponse } from "../api/types";
import { apiFileUrl } from "../api/client";

export function OutputViewer({
  jobId,
  output,
  outputFiles,
}: {
  jobId: string;
  output: JobOutputResponse;
  outputFiles: string[];
}) {
  const { book, pdf } = output;
  const report = book.report;

  return (
    <div className="space-y-6">
      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Chapters" value={report.total_chapters} />
        <Stat label="Words" value={report.total_words.toLocaleString()} />
        {report.total_verses_referenced != null && (
          <Stat label="Verses" value={report.total_verses_referenced} />
        )}
        {pdf && <Stat label="PDF Pages" value={pdf.total_pages} />}
      </div>

      {/* Download buttons */}
      <div className="flex flex-wrap gap-3">
        {outputFiles.map((filename) => (
          <a
            key={filename}
            href={apiFileUrl(jobId, filename)}
            download
            className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 no-underline"
          >
            {filename.endsWith(".pdf") ? "\u{1F4C4}" : "\u{1F4DD}"} {filename}
          </a>
        ))}
      </div>

      {/* Markdown preview */}
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <div className="prose prose-slate max-w-none">
          <Markdown>{book.full_book_markdown}</Markdown>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-xl font-semibold text-gray-900">{value}</p>
    </div>
  );
}
