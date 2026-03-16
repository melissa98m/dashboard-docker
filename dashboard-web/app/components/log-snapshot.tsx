import type { Ref } from "react";

interface LogSnapshotProps {
  lines: string[];
  title: string;
  subtitle?: string;
  emptyLabel?: string;
  maxHeightClassName?: string;
  viewportRef?: Ref<HTMLDivElement>;
  ariaLive?: "off" | "polite";
}

export function splitLogLines(text: string): string[] {
  if (text.length === 0) return [];
  return text.replace(/\r\n/g, "\n").split("\n");
}

export function LogSnapshot({
  lines,
  title,
  subtitle,
  emptyLabel = "Aucun log",
  maxHeightClassName,
  viewportRef,
  ariaLive = "off",
}: LogSnapshotProps) {
  const countLabel = `${lines.length} ligne${lines.length > 1 ? "s" : ""}`;
  const viewportClassName = maxHeightClassName
    ? `log-snapshot-viewport ${maxHeightClassName}`
    : "log-snapshot-viewport";

  return (
    <div className="log-snapshot">
      <div className="log-snapshot-header">
        <div>
          <p className="font-semibold">{title}</p>
          {subtitle ? <p className="log-snapshot-subtitle">{subtitle}</p> : null}
        </div>
        <span className="log-snapshot-count">{countLabel}</span>
      </div>

      <div
        ref={viewportRef}
        className={viewportClassName}
        role="log"
        aria-label={title}
        aria-live={ariaLive}
      >
        {lines.length === 0 ? (
          <p className="log-snapshot-empty">{emptyLabel}</p>
        ) : (
          <ol className="log-snapshot-lines">
            {lines.map((line, index) => (
              <li key={`${index}-${line.slice(0, 24)}`} className="log-snapshot-line">
                <span className="log-snapshot-line-number" aria-hidden="true">
                  {index + 1}
                </span>
                <code className="log-snapshot-line-text">{line || " "}</code>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
