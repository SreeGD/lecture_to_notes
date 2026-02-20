import { useMemo } from "react";
import type { BrowseEntry } from "../api/types";

// ---------- Color palette for categories ----------

const CATEGORY_COLORS: Record<string, { bg: string; text: string; hover: string }> = {
  prabhupada: { bg: "bg-amber-500", text: "text-amber-950", hover: "hover:bg-amber-400" },
  swamis: { bg: "bg-blue-500", text: "text-blue-950", hover: "hover:bg-blue-400" },
  prabhujis: { bg: "bg-emerald-500", text: "text-emerald-950", hover: "hover:bg-emerald-400" },
  matajis: { bg: "bg-purple-500", text: "text-purple-950", hover: "hover:bg-purple-400" },
  more: { bg: "bg-slate-500", text: "text-slate-950", hover: "hover:bg-slate-400" },
  default: { bg: "bg-cyan-500", text: "text-cyan-950", hover: "hover:bg-cyan-400" },
};

function getCategoryColor(name: string, path: string) {
  const lower = (name + " " + path).toLowerCase();
  if (lower.includes("prabhupada")) return CATEGORY_COLORS.prabhupada;
  if (lower.includes("swami")) return CATEGORY_COLORS.swamis;
  if (lower.includes("prabhuji") || lower.includes("prabhu")) return CATEGORY_COLORS.prabhujis;
  if (lower.includes("mataji")) return CATEGORY_COLORS.matajis;
  if (lower.includes("more")) return CATEGORY_COLORS.more;
  return CATEGORY_COLORS.default;
}

// ---------- Count parsing ----------

function parseCount(size: string | null): number {
  if (!size) return 1;
  const match = size.match(/(\d+)/);
  return match ? Math.max(parseInt(match[1], 10), 1) : 1;
}

// ---------- Squarified treemap layout ----------

interface TreeNode {
  entry: BrowseEntry;
  count: number;
}

interface LayoutRect {
  node: TreeNode;
  x: number;
  y: number;
  w: number;
  h: number;
}

function worstRatio(row: TreeNode[], totalArea: number, side: number): number {
  if (row.length === 0) return Infinity;
  const rowArea = row.reduce((s, n) => s + n.count, 0) * (totalArea > 0 ? 1 : 0);
  const scaledAreas = row.map((n) => (n.count / totalArea) * (side * side) || 0);
  const sumArea = scaledAreas.reduce((a, b) => a + b, 0);
  if (sumArea === 0 || side === 0) return Infinity;
  const rowWidth = sumArea / side;
  let worst = 0;
  for (const area of scaledAreas) {
    const h = area / rowWidth || 0;
    const ratio = Math.max(rowWidth / h, h / rowWidth);
    worst = Math.max(worst, ratio);
  }
  return worst;
}

function squarify(
  nodes: TreeNode[],
  rect: { x: number; y: number; w: number; h: number },
): LayoutRect[] {
  if (nodes.length === 0) return [];

  const totalCount = nodes.reduce((s, n) => s + n.count, 0);
  if (totalCount === 0) return [];

  const results: LayoutRect[] = [];
  const sorted = [...nodes].sort((a, b) => b.count - a.count);

  let remaining = sorted;
  let { x, y, w, h } = rect;

  while (remaining.length > 0) {
    const side = Math.min(w, h);
    const totalArea = w * h;
    const remainingCount = remaining.reduce((s, n) => s + n.count, 0);

    const row: TreeNode[] = [remaining[0]];
    let rest = remaining.slice(1);

    // Add items to row while aspect ratio improves
    while (rest.length > 0) {
      const candidate = [...row, rest[0]];
      if (worstRatio(candidate, remainingCount, side) <= worstRatio(row, remainingCount, side)) {
        row.push(rest[0]);
        rest = rest.slice(1);
      } else {
        break;
      }
    }

    // Layout this row
    const rowCount = row.reduce((s, n) => s + n.count, 0);
    const rowFraction = rowCount / remainingCount;

    if (w >= h) {
      // Place row on the left
      const rowWidth = w * rowFraction;
      let cy = y;
      for (const node of row) {
        const nodeHeight = (node.count / rowCount) * h;
        results.push({ node, x, y: cy, w: rowWidth, h: nodeHeight });
        cy += nodeHeight;
      }
      x += rowWidth;
      w -= rowWidth;
    } else {
      // Place row on top
      const rowHeight = h * rowFraction;
      let cx = x;
      for (const node of row) {
        const nodeWidth = (node.count / rowCount) * w;
        results.push({ node, x: cx, y, w: nodeWidth, h: rowHeight });
        cx += nodeWidth;
      }
      y += rowHeight;
      h -= rowHeight;
    }

    remaining = rest;
  }

  return results;
}

// ---------- Component ----------

interface TopicTreeMapProps {
  entries: BrowseEntry[];
  currentPath: string;
  onNavigate: (path: string) => void;
}

export function TopicTreeMap({ entries, currentPath, onNavigate }: TopicTreeMapProps) {
  const folders = useMemo(
    () => entries.filter((e) => e.is_dir),
    [entries],
  );

  const nodes: TreeNode[] = useMemo(
    () => folders.map((entry) => ({ entry, count: parseCount(entry.size) })),
    [folders],
  );

  const totalItems = nodes.reduce((s, n) => s + n.count, 0);

  const layout = useMemo(() => {
    if (nodes.length === 0) return [];
    return squarify(nodes, { x: 0, y: 0, w: 100, h: 100 });
  }, [nodes]);

  if (folders.length === 0) {
    return (
      <div className="p-4 text-sm text-gray-500">
        No sub-topics found at this level. Switch to list view to see files.
      </div>
    );
  }

  return (
    <div className="p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs text-gray-500">
          {folders.length} topic{folders.length !== 1 ? "s" : ""} &middot;{" "}
          {totalItems} total items
        </span>
        <span className="text-xs text-gray-400">Click to drill down</span>
      </div>
      <div
        className="relative overflow-hidden rounded-lg border border-gray-200"
        style={{ width: "100%", paddingBottom: "60%" }}
      >
        {layout.map((rect) => {
          const colors = getCategoryColor(rect.node.entry.name, currentPath);
          const isSmall = rect.w < 12 || rect.h < 12;
          const isTiny = rect.w < 8 || rect.h < 8;
          return (
            <button
              key={rect.node.entry.href}
              onClick={() => onNavigate(rect.node.entry.href)}
              title={`${rect.node.entry.name}${rect.node.entry.size ? ` (${rect.node.entry.size})` : ""}`}
              className={`absolute overflow-hidden border border-white/30 transition-all duration-150 ${colors.bg} ${colors.text} ${colors.hover} cursor-pointer`}
              style={{
                left: `${rect.x}%`,
                top: `${rect.y}%`,
                width: `${rect.w}%`,
                height: `${rect.h}%`,
              }}
            >
              {!isTiny && (
                <div className={`flex h-full flex-col justify-center p-1 ${isSmall ? "items-center" : "items-start px-2"}`}>
                  <span
                    className={`font-medium leading-tight ${
                      isSmall ? "text-[9px]" : rect.w < 20 ? "text-[10px]" : "text-xs"
                    } line-clamp-2`}
                  >
                    {rect.node.entry.name
                      .replace(/_/g, " ")
                      .replace(/^\d+\s*-\s*/, "")}
                  </span>
                  {!isSmall && rect.node.entry.size && (
                    <span className="mt-0.5 text-[9px] opacity-70">
                      {rect.node.entry.size}
                    </span>
                  )}
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
