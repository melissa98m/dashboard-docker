"use client";

interface PaginationControlsProps {
  total: number;
  page: number;
  pageSize: number;
  itemLabel?: string;
  pageSizeOptions?: number[];
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

export function PaginationControls({
  total,
  page,
  pageSize,
  itemLabel = "élément",
  pageSizeOptions = [5, 10, 25, 50, 100],
  onPageChange,
  onPageSizeChange,
}: PaginationControlsProps) {
  const safeTotal = Math.max(0, total);
  const safePageSize = Math.max(1, pageSize);
  const totalPages = Math.max(1, Math.ceil(safeTotal / safePageSize));
  const currentPage = Math.min(Math.max(1, page), totalPages);
  const start = safeTotal === 0 ? 0 : (currentPage - 1) * safePageSize + 1;
  const end =
    safeTotal === 0 ? 0 : Math.min(safeTotal, currentPage * safePageSize);
  const itemLabelPlural = safeTotal > 1 ? `${itemLabel}s` : itemLabel;
  const isEmpty = safeTotal === 0;

  return (
    <div className="pagination-shell">
      <div className="pagination-meta">
        <div>
          <p className="pagination-label">Pagination</p>
          <div className="pagination-count">
            <span className="pagination-range-chip">
              {isEmpty ? "0" : `${start}-${end}`}
            </span>
            <span>
              sur {safeTotal} {itemLabelPlural}
            </span>
          </div>
        </div>
      </div>

      <div className="pagination-actions">
        <label className="pagination-select-group">
          <span>Par page</span>
          <select
            value={String(safePageSize)}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
            className="pagination-select"
            aria-label="Taille de page"
          >
            {pageSizeOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <div className="pagination-nav">
          <button
            type="button"
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage <= 1}
            className="btn btn-neutral pagination-nav-button disabled:cursor-not-allowed disabled:opacity-50"
          >
            ← Précédent
          </button>
          <span className="pagination-page-indicator">
            Page {currentPage}/{totalPages}
          </span>
          <button
            type="button"
            onClick={() => onPageChange(currentPage + 1)}
            disabled={currentPage >= totalPages}
            className="btn btn-neutral pagination-nav-button disabled:cursor-not-allowed disabled:opacity-50"
          >
            Suivant →
          </button>
        </div>
      </div>
    </div>
  );
}
