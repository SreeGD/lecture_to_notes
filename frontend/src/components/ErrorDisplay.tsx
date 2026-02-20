export function ErrorDisplay({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4">
      <p className="text-sm font-medium text-red-800">Error</p>
      <p className="mt-1 text-sm text-red-700">{message}</p>
    </div>
  );
}
