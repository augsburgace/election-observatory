import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  Check,
  ChevronDown,
  Download,
  Expand,
  FileSearch,
  Info,
  LoaderCircle,
  Minimize,
  MoreHorizontal,
  X,
} from "lucide-react";
import { compact, dateLabel, fmt, human } from "../utils";
export function Badge({
  children,
  tone = "muted",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return (
    <span className={`badge ${tone}`}>
      <span className="status-dot" />
      {children}
    </span>
  );
}
export function Stat({
  label,
  value,
  detail,
  icon,
  accent = "cyan",
}: {
  label: string;
  value: ReactNode;
  detail: ReactNode;
  icon: ReactNode;
  accent?: string;
}) {
  return (
    <section className={`stat ${accent}`}>
      <div className="stat-icon">{icon}</div>
      <div>
        <p className="stat-label">{label}</p>
        <strong>{value}</strong>
        <div className="stat-detail">{detail}</div>
      </div>
    </section>
  );
}
export function Empty({
  title,
  children,
  icon,
  action,
}: {
  title: string;
  children: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-symbol">{icon || <FileSearch size={26} />}</div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function Notice({
  children,
  tone = "info",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return (
    <div className={`notice ${tone}`}>
      {tone === "warning" ? <AlertTriangle size={16} /> : <Info size={16} />}
      <div>{children}</div>
    </div>
  );
}
export function Loading({
  label = "Loading validated evidence…",
}: {
  label?: string;
}) {
  return (
    <div className="loading">
      <LoaderCircle size={22} className="spin" />
      <span>{label}</span>
    </div>
  );
}
export function ExternalLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="external">
      {children}
      <ArrowUpRight size={13} />
    </a>
  );
}
export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function Select({
  value,
  onChange,
  options,
  label,
}: {
  value: string | number;
  onChange: (v: string) => void;
  options: { value: string | number; label: string; disabled?: boolean }[];
  label?: string;
}) {
  return (
    <div className="select-wrap">
      <select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value} disabled={o.disabled}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown size={13} />
    </div>
  );
}
export function Segmented<T extends string>({
  value,
  items,
  onChange,
  label,
}: {
  value: T;
  items: { id: T; label: string; icon?: ReactNode; disabled?: boolean }[];
  onChange: (id: T) => void;
  label: string;
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {items.map((item) => (
        <button
          key={item.id}
          className={item.id === value ? "active" : ""}
          onClick={() => onChange(item.id)}
          disabled={item.disabled}
          aria-pressed={value === item.id}
        >
          {item.icon}
          {item.label}
        </button>
      ))}
    </div>
  );
}
async function exportSvg(
  root: HTMLElement,
  name: string,
  footer: string,
  format: "svg" | "png",
) {
  const source = root.querySelector(
    "svg.recharts-surface,svg.map-svg,svg.poll-forest",
  );
  if (!source) {
    const canvas = root.querySelector(
      "canvas.maplibregl-canvas",
    ) as HTMLCanvasElement | null;
    if (canvas && format === "png") {
      const out = document.createElement("canvas");
      out.width = canvas.width;
      out.height = canvas.height + 45;
      const context = out.getContext("2d")!;
      context.fillStyle = "#102033";
      context.fillRect(0, 0, out.width, out.height);
      context.drawImage(canvas, 0, 0);
      context.fillStyle = "#b9cadc";
      context.font = "12px Arial";
      context.fillText(footer, 12, out.height - 17);
      const a = document.createElement("a");
      a.href = out.toDataURL("image/png");
      a.download = `${name}.png`;
      a.click();
      return;
    }
    throw new Error(
      "For SVG export, switch the geographic map to Vector view. PNG export supports the interactive map.",
    );
  }
  const clone = source.cloneNode(true) as SVGSVGElement;
  const rect = source.getBoundingClientRect();
  const width = Number(source.getAttribute("width")) || rect.width || 900;
  const height = Number(source.getAttribute("height")) || rect.height || 400;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute(
    "style",
    "--map-land:#172a3a;--map-stroke:#5d7488;--map-missing:#1f2c3c;--cyan:#25cfd4;--gold:#ffcb70;--text:#e8f0fa;--muted:#a6b8cd;--panel:#102033;--chart-grid:#263b4d",
  );
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height + 40));
  clone.setAttribute("viewBox", `0 0 ${width} ${height + 40}`);
  const style = document.createElementNS("http://www.w3.org/2000/svg", "style");
  style.textContent =
    "text{font-family:Arial,sans-serif;fill:#b9cadc}.recharts-cartesian-grid line{stroke:#274058}";
  clone.insertBefore(style, clone.firstChild);
  const background = document.createElementNS(
    "http://www.w3.org/2000/svg",
    "rect",
  );
  background.setAttribute("width", "100%");
  background.setAttribute("height", "100%");
  background.setAttribute("fill", "#102033");
  clone.insertBefore(background, clone.firstChild);
  const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
  text.setAttribute("x", "12");
  text.setAttribute("y", String(height + 25));
  text.setAttribute("font-size", "10");
  text.textContent = footer;
  clone.appendChild(text);
  const svg = new XMLSerializer().serializeToString(clone);
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  if (format === "svg") {
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name}.svg`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return;
  }
  const image = new Image();
  image.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = width * 2;
    canvas.height = (height + 40) * 2;
    canvas
      .getContext("2d")!
      .drawImage(image, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (!blob) return;
      const png = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = png;
      a.download = `${name}.png`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(png), 1000);
    }, "image/png");
    URL.revokeObjectURL(url);
  };
  image.src = url;
}
export function Panel({
  title,
  subtitle,
  children,
  actions,
  className = "",
  exportLabel,
  footnote,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
  exportLabel?: string;
  footnote?: ReactNode;
}) {
  const ref = useRef<HTMLElement>(null);
  const [full, setFull] = useState(false);
  const [menu, setMenu] = useState(false);
  const [error, setError] = useState("");
  return (
    <section
      ref={ref}
      className={`panel ${className} ${full ? "panel-fullscreen" : ""}`}
    >
      <header className="panel-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <div className="panel-actions">
          {actions}
          <button
            className="icon-button panel-expand"
            aria-label={full ? "Exit full screen" : "Expand panel"}
            onClick={() => setFull(!full)}
          >
            {full ? <Minimize size={15} /> : <Expand size={15} />}
          </button>
          {exportLabel && (
            <div className="dropdown">
              <button
                className="icon-button"
                aria-label="Export chart"
                onClick={() => setMenu(!menu)}
              >
                <MoreHorizontal size={17} />
              </button>
              {menu && (
                <div className="dropdown-menu">
                  {(["svg", "png"] as const).map((format) => (
                    <button
                      key={format}
                      onClick={() => {
                        setMenu(false);
                        exportSvg(
                          ref.current!,
                          String(title).replaceAll(" ", "-").toLowerCase(),
                          exportLabel,
                          format,
                        ).catch((e) => setError(e.message));
                      }}
                    >
                      <Download size={14} />
                      Export {format.toUpperCase()}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </header>
      {error && <Notice tone="warning">{error}</Notice>}
      <div className="panel-body">{children}</div>
      {footnote && <div className="panel-foot">{footnote}</div>}
    </section>
  );
}
export function Datum({
  label,
  value,
  detail,
}: {
  label: string;
  value: unknown;
  detail?: ReactNode;
}) {
  return (
    <div className="datum">
      <span>{label}</span>
      <strong>
        {typeof value === "number" ? fmt(value) : String(value ?? "—")}
      </strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}
export function SourceDate({ value }: { value?: string | null }) {
  return <time dateTime={value || undefined}>{dateLabel(value)}</time>;
}
export function Status({ value }: { value: string }) {
  const tone = [
    "ready",
    "current",
    "unchanged",
    "validated",
    "complete",
    "available",
  ].includes(value)
    ? "teal"
    : ["failed", "error"].includes(value)
      ? "red"
      : ["partial", "stale"].includes(value)
        ? "amber"
        : "muted";
  return <Badge tone={tone}>{human(value)}</Badge>;
}
export function MiniBar({
  value,
  max,
  color = "var(--cyan)",
}: {
  value: number | null | undefined;
  max: number;
  color?: string;
}) {
  return (
    <div className="mini-bar">
      <span
        style={{
          width: `${value == null ? 0 : Math.max(1, Math.min(100, (value / Math.max(max, 1)) * 100))}%`,
          background: color,
        }}
      />
      <span className="mini-bar-value">{compact(value)}</span>
    </div>
  );
}
export function Toast({
  message,
  onClose,
}: {
  message: string;
  onClose: () => void;
}) {
  return (
    <div className="toast" role="status">
      <Check size={17} />
      {message}
      <button
        className="icon-button"
        onClick={onClose}
        aria-label="Dismiss notification"
      >
        <X size={15} />
      </button>
    </div>
  );
}

/** Restore the trigger and keep keyboard interaction inside an active dialog. */
export function useModalFocus(
  active: boolean,
  selector: string,
  onClose: () => void,
) {
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!active) return;
    const dialog = document.querySelector<HTMLElement>(selector);
    if (!dialog) return;
    const previous = document.activeElement as HTMLElement | null;
    const nodes = () =>
      Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]',
        ),
      ).filter((node) => node.offsetParent !== null);
    const frame = requestAnimationFrame(() => nodes()[0]?.focus());
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close.current();
        return;
      }
      if (event.key !== "Tab") return;
      const items = nodes();
      if (!items.length) {
        event.preventDefault();
        return;
      }
      const first = items[0],
        last = items.at(-1)!;
      if (
        event.shiftKey &&
        (document.activeElement === first ||
          !dialog.contains(document.activeElement))
      ) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last ||
          !dialog.contains(document.activeElement))
      ) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", keydown);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("keydown", keydown);
      previous?.focus();
    };
  }, [active, selector]);
}
