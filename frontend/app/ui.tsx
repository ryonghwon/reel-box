import { type MediaJob, labels, duration } from "./media";

const shapes: Record<string, React.ReactNode> = {
  compact: (
    <>
      {[3, 10, 17].flatMap((x) =>
        [3, 10, 17].map((y) => (
          <rect key={`${x}-${y}`} x={x} y={y} width="4" height="4" rx=".7" />
        )),
      )}
    </>
  ),
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="m16 16 5 5" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  bookmark: <path d="M6 3h12v18l-6-4-6 4Z" />,
  list: (
    <>
      <path d="M9 6h12M9 12h12M9 18h12M3 6h1M3 12h1M3 18h1" />
    </>
  ),
  external: (
    <>
      <path d="M14 3h7v7m0-7L10 14M10 3H3v18h18v-7" />
    </>
  ),
  chevron: <path d="m9 5 7 7-7 7" />,
  upload: (
    <>
      <path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5" />
    </>
  ),
  music: (
    <>
      <path d="M9 18V5l11-2v13M9 8l11-2" />
      <ellipse cx="6" cy="18" rx="3" ry="2" />
      <ellipse cx="17" cy="16" rx="3" ry="2" />
    </>
  ),
  download: (
    <>
      <path d="M12 3v12m-5-5 5 5 5-5" />
      <path d="M4 15v5h16v-5" />
    </>
  ),
  grid: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </>
  ),
  video: (
    <>
      <rect x="3" y="5" width="13" height="14" rx="3" />
      <path d="m16 10 5-3v10l-5-3" />
    </>
  ),
  settings: (
    <>
      <path d="M4 7h16M4 17h16" />
      <circle cx="9" cy="7" r="3" />
      <circle cx="15" cy="17" r="3" />
    </>
  ),
  link: (
    <>
      <path
        d="m10 14 4-4m-6 6-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 2 1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0"
        transform="translate(1 -1)"
      />
    </>
  ),
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  check: <path d="m5 12 4 4L19 6" />,
  refresh: (
    <>
      <path d="M20 7v5h-5M4 17v-5h5" />
      <path d="M6 7a7 7 0 0 1 12-2l2 3M4 16l2 3a7 7 0 0 0 12-2" />
    </>
  ),
  folder: <path d="M3 6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v10H3Z" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  close: <path d="m6 6 12 12M6 18 18 6" />,
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v6m0-10v1" />
    </>
  ),
  play: <path d="m9 5 11 7-11 7Z" />,
  file: (
    <>
      <path d="M6 3h8l4 4v14H6Z" />
      <path d="M14 3v5h4M9 13h6m-6 4h4" />
    </>
  ),
  trash: (
    <>
      <path d="M3 6h18M9 3h6m-9 3 1 15h10l1-15M10 10v7m4-7v7" />
    </>
  ),
};

export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {shapes[name] || shapes.file}
    </svg>
  );
}

export function Status({ job }: { job: MediaJob }) {
  return (
    <span className={`status ${job.status}`}>
      <span className="dot" />
      {labels[job.status] || job.status}
      {job.status === "downloading" ? ` ${Math.round(job.progress)}%` : ""}
    </span>
  );
}
export function Thumbnail({ job }: { job: MediaJob }) {
  return (
    <div className="thumbnail">
      <Icon
        name={
          job.metadata.media_type === "image_group"
            ? "grid"
            : job.mode === "audio"
              ? "music"
              : "video"
        }
        size={28}
      />
      {job.metadata.thumbnail ? (
        <img
          key={job.metadata.thumbnail}
          src={job.metadata.thumbnail}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={(e) => {
            e.currentTarget.style.display = "none";
          }}
        />
      ) : null}
      <span className="duration">{duration(job.metadata.duration)}</span>
      {job.status === "downloading" ? (
        <div className="progress">
          <div style={{ width: `${job.progress}%` }} />
        </div>
      ) : null}
    </div>
  );
}
