import { useCallback, useEffect, useRef, useState } from "react";
import { browseAudio, searchAudio } from "../api/jobs";
import type { BrowseEntry, SearchGroup } from "../api/types";
import { TopicBrowser } from "./TopicBrowser";
import { TopicTreeMap } from "./TopicTreeMap";

const ISKCON_BASE = "https://audio.iskcondesiretree.com";

type ViewMode = "list" | "treemap";
type BrowseTab = "browse" | "topics";

interface AudioBrowserProps {
  onAdd: (urls: string[]) => void;
  onClose: () => void;
}

export function AudioBrowser({ onAdd, onClose }: AudioBrowserProps) {
  // Browse state
  const [currentPath, setCurrentPath] = useState("/");
  const [entries, setEntries] = useState<BrowseEntry[]>([]);
  const [parentPath, setParentPath] = useState<string | null>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchGroups, setSearchGroups] = useState<SearchGroup[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [isSearchMode, setIsSearchMode] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    new Set(),
  );

  // View mode and tab
  const [viewMode, setViewMode] = useState<ViewMode>("treemap");
  const [activeTab, setActiveTab] = useState<BrowseTab>("browse");

  // Shared state
  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const searchInputRef = useRef<HTMLInputElement>(null);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout>>();

  const fetchDir = useCallback(async (path: string) => {
    setLoading(true);
    setError(null);
    setIsSearchMode(false);
    try {
      const resp = await browseAudio(path);
      setEntries(resp.entries);
      setParentPath(resp.parent);
      setCurrentPath(resp.path);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to browse");
    } finally {
      setLoading(false);
    }
  }, []);

  const doSearch = useCallback(async (query: string) => {
    if (query.trim().length < 2) return;
    setLoading(true);
    setError(null);
    setIsSearchMode(true);
    try {
      const resp = await searchAudio(query.trim());
      setSearchGroups(resp.groups);
      setSearchTotal(resp.total);
      setCollapsedGroups(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDir("/");
  }, [fetchDir]);

  const navigateTo = (path: string) => {
    setSearchQuery("");
    setActiveTab("browse");
    fetchDir(path);
  };

  const handleSearchInput = (value: string) => {
    setSearchQuery(value);
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    if (value.trim().length >= 2) {
      searchTimerRef.current = setTimeout(() => doSearch(value), 500);
    } else if (value.trim().length === 0) {
      setIsSearchMode(false);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    if (searchQuery.trim().length >= 2) {
      doSearch(searchQuery);
    }
  };

  const clearSearch = () => {
    setSearchQuery("");
    setIsSearchMode(false);
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchInputRef.current?.focus();
  };

  const toggleSelect = (href: string) => {
    const url = `${ISKCON_BASE}${href}`;
    setSelectedUrls((prev) => {
      const next = new Set(prev);
      if (next.has(url)) {
        next.delete(url);
      } else {
        next.add(url);
      }
      return next;
    });
  };

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

  const handleAdd = () => {
    onAdd(Array.from(selectedUrls));
    onClose();
  };

  // Build breadcrumb segments from currentPath
  const breadcrumbs = currentPath
    .split("/")
    .filter(Boolean)
    .map((seg, i, arr) => ({
      label: seg.replace(/_/g, " ").replace(/^\d+\s*-\s*/, ""),
      path: "/" + arr.slice(0, i + 1).join("/"),
    }));

  const hasFolders = entries.some((e) => e.is_dir);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-lg bg-white shadow-xl">
        {/* Header + Tabs */}
        <div className="border-b">
          <div className="flex items-center justify-between px-4 pt-3 pb-0">
            <h3 className="text-lg font-semibold text-gray-900">
              ISKCON Desire Tree Audio
            </h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 text-xl leading-none"
            >
              &times;
            </button>
          </div>
          <div className="flex gap-0 px-4 mt-2">
            <button
              onClick={() => setActiveTab("browse")}
              className={`px-3 py-1.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === "browse"
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              Browse
            </button>
            <button
              onClick={() => setActiveTab("topics")}
              className={`px-3 py-1.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === "topics"
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              Topics
            </button>
          </div>
        </div>

        {/* Search bar + view toggle (browse tab only) */}
        {activeTab === "browse" && <div className="flex items-center gap-2 border-b px-4 py-2">
          <form onSubmit={handleSearchSubmit} className="flex-1">
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                &#128269;
              </span>
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => handleSearchInput(e.target.value)}
                placeholder="Search by title (e.g. Bhagavad Gita, Gaura Purnima)"
                className="w-full rounded-md border border-gray-300 py-1.5 pl-8 pr-8 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={clearSearch}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-sm"
                >
                  &times;
                </button>
              )}
            </div>
          </form>
          {/* View toggle (only in browse mode with folders) */}
          {!isSearchMode && hasFolders && (
            <div className="flex rounded-md border border-gray-300 overflow-hidden shrink-0">
              <button
                onClick={() => setViewMode("list")}
                className={`px-2 py-1.5 text-xs ${
                  viewMode === "list"
                    ? "bg-blue-600 text-white"
                    : "bg-white text-gray-600 hover:bg-gray-50"
                }`}
                title="List view"
              >
                &#9776;
              </button>
              <button
                onClick={() => setViewMode("treemap")}
                className={`px-2 py-1.5 text-xs ${
                  viewMode === "treemap"
                    ? "bg-blue-600 text-white"
                    : "bg-white text-gray-600 hover:bg-gray-50"
                }`}
                title="Topic map"
              >
                &#9638;
              </button>
            </div>
          )}
        </div>}

        {/* Breadcrumb (only in browse tab) */}
        {activeTab === "browse" && !isSearchMode && (
          <div className="flex flex-wrap items-center gap-1 border-b bg-gray-50 px-4 py-2 text-sm">
            <button
              onClick={() => navigateTo("/")}
              className="text-blue-600 hover:text-blue-800"
            >
              Root
            </button>
            {breadcrumbs.map((bc) => (
              <span key={bc.path} className="flex items-center gap-1">
                <span className="text-gray-400">/</span>
                <button
                  onClick={() => navigateTo(bc.path)}
                  className="text-blue-600 hover:text-blue-800 truncate max-w-[200px]"
                  title={bc.label}
                >
                  {bc.label}
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Search results summary */}
        {activeTab === "browse" && isSearchMode && !loading && !error && (
          <div className="flex items-center justify-between border-b bg-blue-50 px-4 py-2 text-sm">
            <span className="text-blue-700">
              {searchTotal} result{searchTotal !== 1 ? "s" : ""} for &ldquo;
              {searchQuery}&rdquo; in {searchGroups.length} group
              {searchGroups.length !== 1 ? "s" : ""}
            </span>
            <button
              onClick={clearSearch}
              className="text-blue-600 hover:text-blue-800 text-xs"
            >
              Back to browsing
            </button>
          </div>
        )}

        {/* Content */}
        <div className="min-h-0 flex-1 overflow-y-auto">
          {/* Topics tab */}
          {activeTab === "topics" && (
            <TopicBrowser
              selectedUrls={selectedUrls}
              onToggleSelect={toggleSelect}
              onNavigate={navigateTo}
            />
          )}

          {/* Browse tab content */}
          {activeTab === "browse" && loading && (
            <div className="flex items-center justify-center py-12">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
              <span className="ml-2 text-sm text-gray-500">
                {isSearchMode ? "Searching..." : "Loading..."}
              </span>
            </div>
          )}

          {activeTab === "browse" && error && (
            <div className="p-4 text-sm text-red-600">
              {error}
              <button
                onClick={() =>
                  isSearchMode ? doSearch(searchQuery) : fetchDir(currentPath)
                }
                className="ml-2 text-blue-600 hover:underline"
              >
                Retry
              </button>
            </div>
          )}

          {/* Browse mode — Tree Map */}
          {activeTab === "browse" && !loading && !error && !isSearchMode && viewMode === "treemap" && (
            <>
              <TopicTreeMap
                entries={entries}
                currentPath={currentPath}
                onNavigate={navigateTo}
              />
              {/* Show files below the treemap if any */}
              {entries.some((e) => !e.is_dir) && (
                <div className="border-t divide-y divide-gray-100">
                  <div className="px-4 py-1.5 bg-gray-50 text-xs text-gray-500 font-medium">
                    Audio files
                  </div>
                  {entries
                    .filter((e) => !e.is_dir)
                    .map((entry) => {
                      const url = `${ISKCON_BASE}${entry.href}`;
                      const isSelected = selectedUrls.has(url);
                      return (
                        <div
                          key={entry.href}
                          className={`flex items-center gap-3 px-4 py-2 text-sm ${
                            isSelected ? "bg-blue-50" : "hover:bg-gray-50"
                          }`}
                        >
                          <div className="flex flex-1 items-center gap-2 min-w-0">
                            <span className="text-blue-500 text-lg">
                              &#127925;
                            </span>
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
                            onClick={() => toggleSelect(entry.href)}
                            className={`shrink-0 rounded px-2 py-1 text-xs font-medium ${
                              isSelected
                                ? "bg-red-100 text-red-700 hover:bg-red-200"
                                : "bg-blue-100 text-blue-700 hover:bg-blue-200"
                            }`}
                          >
                            {isSelected ? "Remove" : "Add"}
                          </button>
                        </div>
                      );
                    })}
                </div>
              )}
            </>
          )}

          {/* Browse mode — List */}
          {activeTab === "browse" && !loading && !error && !isSearchMode && viewMode === "list" && (
            <div className="divide-y divide-gray-100">
              {entries.length === 0 && (
                <div className="p-4 text-sm text-gray-500">
                  No directories or MP3 files found.
                </div>
              )}
              {parentPath && (
                <button
                  onClick={() => navigateTo(parentPath)}
                  className="flex w-full items-center gap-3 px-4 py-2 text-left text-sm hover:bg-gray-50"
                >
                  <span className="text-lg">&#8617;</span>
                  <span className="text-gray-600">Parent directory</span>
                </button>
              )}
              {entries.map((entry) => {
                const url = `${ISKCON_BASE}${entry.href}`;
                const isSelected = selectedUrls.has(url);
                return (
                  <div
                    key={entry.href}
                    className={`flex items-center gap-3 px-4 py-2 text-sm ${
                      isSelected ? "bg-blue-50" : "hover:bg-gray-50"
                    }`}
                  >
                    {entry.is_dir ? (
                      <button
                        onClick={() => navigateTo(entry.href)}
                        className="flex flex-1 items-center gap-2 text-left"
                      >
                        <span className="text-amber-500 text-lg">
                          &#128193;
                        </span>
                        <span className="text-gray-900 truncate">
                          {entry.name}
                        </span>
                      </button>
                    ) : (
                      <>
                        <div className="flex flex-1 items-center gap-2 min-w-0">
                          <span className="text-blue-500 text-lg">
                            &#127925;
                          </span>
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
                          onClick={() => toggleSelect(entry.href)}
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

          {/* Search mode — grouped results */}
          {activeTab === "browse" && !loading && !error && isSearchMode && (
            <div>
              {searchGroups.length === 0 && (
                <div className="p-4 text-sm text-gray-500">
                  No results found. Try different search terms.
                </div>
              )}
              {searchGroups.map((group) => {
                const isCollapsed = collapsedGroups.has(group.group_title);
                return (
                  <div key={group.group_title} className="border-b">
                    {/* Group header */}
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

                    {/* Group entries */}
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
                                  onClick={() => navigateTo(entry.href)}
                                  className="flex flex-1 items-center gap-2 text-left"
                                >
                                  <span className="text-amber-500">
                                    &#128193;
                                  </span>
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
                                    <span className="text-blue-500">
                                      &#127925;
                                    </span>
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
                                    onClick={() => toggleSelect(entry.href)}
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
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t px-4 py-3">
          <span className="text-sm text-gray-600">
            {selectedUrls.size} file{selectedUrls.size !== 1 ? "s" : ""}{" "}
            selected
          </span>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={handleAdd}
              disabled={selectedUrls.size === 0}
              className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Add to Job
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
