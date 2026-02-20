import { useCallback, useEffect, useState } from "react";
import { getTopics, searchAudio } from "../api/jobs";
import type { SearchGroup, TopicCategory, TopicEntry } from "../api/types";

const ISKCON_BASE = "https://audio.iskcondesiretree.com";

const CATEGORY_STYLES: Record<string, { badge: string; card: string }> = {
  scripture: {
    badge: "bg-amber-100 text-amber-800",
    card: "border-amber-200 bg-amber-50 hover:bg-amber-100",
  },
  festival: {
    badge: "bg-rose-100 text-rose-800",
    card: "border-rose-200 bg-rose-50 hover:bg-rose-100",
  },
  theme: {
    badge: "bg-blue-100 text-blue-800",
    card: "border-blue-200 bg-blue-50 hover:bg-blue-100",
  },
  practice: {
    badge: "bg-emerald-100 text-emerald-800",
    card: "border-emerald-200 bg-emerald-50 hover:bg-emerald-100",
  },
};

interface TopicBrowserProps {
  selectedUrls: Set<string>;
  onToggleSelect: (href: string) => void;
  onNavigate: (path: string) => void;
}

export function TopicBrowser({
  selectedUrls,
  onToggleSelect,
  onNavigate,
}: TopicBrowserProps) {
  const [categories, setCategories] = useState<TopicCategory[]>([]);
  const [selectedTopic, setSelectedTopic] = useState<TopicEntry | null>(null);
  const [searchGroups, setSearchGroups] = useState<SearchGroup[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    new Set(),
  );
  const [loading, setLoading] = useState(false);
  const [loadingTopics, setLoadingTopics] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTopics()
      .then((resp) => setCategories(resp.categories))
      .catch(() => setError("Failed to load topics"))
      .finally(() => setLoadingTopics(false));
  }, []);

  const selectTopic = useCallback(async (topic: TopicEntry) => {
    setSelectedTopic(topic);
    setLoading(true);
    setError(null);
    try {
      // Search using the first search term (most specific)
      const resp = await searchAudio(topic.search_terms[0]);
      setSearchGroups(resp.groups);
      setSearchTotal(resp.total);
      setCollapsedGroups(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const toggleGroup = (title: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(title)) {
        next.delete(title);
      } else {
        next.add(title);
      }
      return next;
    });
  };

  const goBack = () => {
    setSelectedTopic(null);
    setSearchGroups([]);
    setSearchTotal(0);
  };

  if (loadingTopics) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
        <span className="ml-2 text-sm text-gray-500">Loading topics...</span>
      </div>
    );
  }

  // Topic drill-down view — show search results grouped by speaker
  if (selectedTopic) {
    const style = CATEGORY_STYLES[selectedTopic.category] || CATEGORY_STYLES.theme;
    return (
      <div>
        {/* Topic header */}
        <div className="flex items-center gap-2 border-b bg-gray-50 px-4 py-2">
          <button
            onClick={goBack}
            className="text-blue-600 hover:text-blue-800 text-sm"
          >
            &larr; All Topics
          </button>
          <span className="text-gray-400">/</span>
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${style.badge}`}>
            {selectedTopic.label}
          </span>
          {!loading && (
            <span className="ml-auto text-xs text-gray-500">
              {searchTotal} result{searchTotal !== 1 ? "s" : ""} in{" "}
              {searchGroups.length} group{searchGroups.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>

        {loading && (
          <div className="flex items-center justify-center py-12">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
            <span className="ml-2 text-sm text-gray-500">
              Searching for {selectedTopic.label}...
            </span>
          </div>
        )}

        {error && (
          <div className="p-4 text-sm text-red-600">
            {error}
            <button
              onClick={() => selectTopic(selectedTopic)}
              className="ml-2 text-blue-600 hover:underline"
            >
              Retry
            </button>
          </div>
        )}

        {!loading && !error && searchGroups.length === 0 && (
          <div className="p-4 text-sm text-gray-500">
            No results found for {selectedTopic.label}.
          </div>
        )}

        {!loading &&
          !error &&
          searchGroups.map((group) => {
            const isCollapsed = collapsedGroups.has(group.group_title);
            return (
              <div key={group.group_title} className="border-b">
                <button
                  onClick={() => toggleGroup(group.group_title)}
                  className="flex w-full items-center gap-2 bg-gray-100 px-4 py-2 text-left hover:bg-gray-200"
                >
                  <span className="text-xs text-gray-500">
                    {isCollapsed ? "\u25B6" : "\u25BC"}
                  </span>
                  <span className="text-sm font-medium text-gray-800 truncate">
                    {group.group_title}
                  </span>
                  <span className="ml-auto text-xs text-gray-500 shrink-0">
                    {group.entries.length} item
                    {group.entries.length !== 1 ? "s" : ""}
                  </span>
                </button>

                {!isCollapsed && (
                  <div className="divide-y divide-gray-50">
                    {group.entries.map((entry) => {
                      const url = `${ISKCON_BASE}${entry.href}`;
                      const isSelected = selectedUrls.has(url);
                      return (
                        <div
                          key={entry.href}
                          className={`flex items-center gap-3 pl-8 pr-4 py-1.5 text-sm ${
                            isSelected ? "bg-blue-50" : "hover:bg-gray-50"
                          }`}
                        >
                          {entry.is_dir ? (
                            <button
                              onClick={() => onNavigate(entry.href)}
                              className="flex flex-1 items-center gap-2 text-left"
                            >
                              <span className="text-amber-500">&#128193;</span>
                              <span className="text-gray-900 truncate">
                                {entry.name}
                              </span>
                              {entry.size && (
                                <span className="text-xs text-gray-400">
                                  ({entry.size})
                                </span>
                              )}
                            </button>
                          ) : (
                            <>
                              <div className="flex flex-1 items-center gap-2 min-w-0">
                                <span className="text-blue-500">&#127925;</span>
                                <span className="text-gray-900 truncate">
                                  {entry.name}
                                </span>
                                {entry.size && (
                                  <span className="ml-auto text-xs text-gray-400 shrink-0">
                                    {entry.size}
                                  </span>
                                )}
                              </div>
                              <button
                                onClick={() => onToggleSelect(entry.href)}
                                className={`shrink-0 rounded px-2 py-1 text-xs font-medium ${
                                  isSelected
                                    ? "bg-red-100 text-red-700 hover:bg-red-200"
                                    : "bg-blue-100 text-blue-700 hover:bg-blue-200"
                                }`}
                              >
                                {isSelected ? "Remove" : "Add"}
                              </button>
                            </>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
      </div>
    );
  }

  // Topic cards view
  return (
    <div className="p-4 space-y-5">
      {categories.map((cat) => {
        const style = CATEGORY_STYLES[cat.category] || CATEGORY_STYLES.theme;
        return (
          <div key={cat.category}>
            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              {cat.label}
            </h4>
            <div className="flex flex-wrap gap-2">
              {cat.topics.map((topic) => (
                <button
                  key={topic.slug}
                  onClick={() => selectTopic(topic)}
                  className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${style.card}`}
                >
                  {topic.label}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
