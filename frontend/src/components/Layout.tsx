import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { checkHealth } from "../api/jobs";

export function Layout({ children }: { children: ReactNode }) {
  const [healthy, setHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    const check = () =>
      checkHealth()
        .then(() => setHealthy(true))
        .catch(() => setHealthy(false));
    check();
    const id = setInterval(check, 15000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link to="/" className="text-xl font-bold text-gray-900 no-underline">
            Lecture to Notes
          </Link>
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <span
              className={`inline-block h-2.5 w-2.5 rounded-full ${
                healthy === null
                  ? "bg-gray-300"
                  : healthy
                    ? "bg-green-500"
                    : "bg-red-500"
              }`}
            />
            API {healthy === null ? "..." : healthy ? "Connected" : "Offline"}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
    </div>
  );
}
