import { useState, useMemo, type ReactNode } from "react";
import { ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react";
import "./DataTable.css";

export interface Column<TData> {
  key: string;
  header: ReactNode;
  cell?: (row: TData) => ReactNode;
  accessor?: (row: TData) => any;
  sortable?: boolean;
  width?: string | number;
}

interface DataTableProps<TData> {
  columns: Column<TData>[];
  data: TData[];
  onRowClick?: (row: TData) => void;
  emptyMessage?: string;
  className?: string;
}

export function DataTable<TData>({
  columns,
  data,
  onRowClick,
  emptyMessage = "No records found.",
  className = "",
}: DataTableProps<TData>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const handleSort = (key: string) => {
    if (sortKey === key) {
      if (sortDir === "asc") setSortDir("desc");
      else {
        setSortKey(null);
        setSortDir("asc");
      }
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sortedData = useMemo(() => {
    if (!sortKey) return data;
    const col = columns.find((c) => c.key === sortKey);
    if (!col) return data;

    return [...data].sort((a, b) => {
      const aVal = col.accessor ? col.accessor(a) : (a as any)[sortKey];
      const bVal = col.accessor ? col.accessor(b) : (b as any)[sortKey];

      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;

      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDir === "asc" ? aVal - bVal : bVal - aVal;
      }

      const aStr = String(aVal).toLowerCase();
      const bStr = String(bVal).toLowerCase();
      return sortDir === "asc"
        ? aStr.localeCompare(bStr)
        : bStr.localeCompare(aStr);
    });
  }, [data, sortKey, sortDir, columns]);

  return (
    <div className={`table-container ${className}`}>
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((col) => {
              const isSorted = sortKey === col.key;
              const canSort = col.sortable ?? true;

              return (
                <th
                  key={col.key}
                  onClick={() => canSort && handleSort(col.key)}
                  className={canSort ? "sortable" : ""}
                  style={{ width: col.width }}
                >
                  <div className="th-content">
                    {col.header}
                    {canSort && (
                      <span className="sort-icon">
                        {isSorted && sortDir === "asc" ? (
                          <ArrowUp size={14} />
                        ) : isSorted && sortDir === "desc" ? (
                          <ArrowDown size={14} />
                        ) : (
                          <ArrowUpDown size={14} className="sort-muted" />
                        )}
                      </span>
                    )}
                  </div>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sortedData.length > 0 ? (
            sortedData.map((row, idx) => (
              <tr
                key={idx}
                onClick={() => onRowClick?.(row)}
                className={onRowClick ? "clickable" : ""}
              >
                {columns.map((col) => (
                  <td key={col.key}>
                    {col.cell
                      ? col.cell(row)
                      : col.accessor
                      ? col.accessor(row)
                      : (row as any)[col.key] ?? "—"}
                  </td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={columns.length} className="empty-cell">
                {emptyMessage}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
