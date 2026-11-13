import { Thumbnail, Status } from "./ui";
import { type MediaJob, names, sizeLabel } from "./media";

type Props = {
  job: MediaJob;
  focused: boolean;
  selected: boolean;
  onFocus: (id: string) => void;
  onToggle: (id: string) => void;
};

export default function MediaCard({
  job: j,
  focused,
  selected,
  onFocus,
  onToggle,
}: Props) {
  return (
    <article
      className={`media-card ${focused ? "focused" : ""} ${selected ? "selected" : ""}`}
    >
      <div className="card-image">
        <button
          className="preview-trigger"
          aria-label={`${j.metadata.title || j.url} 상세 보기`}
          onClick={() => onFocus(j.id)}
        >
          <Thumbnail job={j} />
        </button>
        <input
          className="card-checkbox"
          type="checkbox"
          aria-label={`${j.metadata.title || j.url} 선택`}
          checked={selected}
          onChange={() => onToggle(j.id)}
        />
        <span className="media-format">
          {j.members
            ? j.image_count
              ? `사진 ${j.image_count}장`
              : "종류 확인 중"
            : j.metadata.media_type === "image"
              ? "IMAGE"
              : j.mode === "audio" || j.metadata.media_type === "audio"
                ? "AUDIO"
                : j.files[0]?.name.split(".").pop()?.toUpperCase() || "VIDEO"}
        </span>
      </div>
      <button className="card-copy" onClick={() => onFocus(j.id)}>
        <strong title={j.metadata.title || j.url}>
          {j.metadata.title ||
            j.url.split("/").filter(Boolean).pop() ||
            "미디어 확인 중"}
        </strong>
        <span className="card-author">
          {j.metadata.uploader || names[j.platform]}
          <span>·</span>
          {j.display_caption ||
            (j.metadata.max_height
              ? `${j.metadata.max_height}p`
              : names[j.platform])}
        </span>
      </button>
      <div className="card-bottom">
        <Status job={j} />
        <span>
          {j.members
            ? `${j.completed_count || 0}/${j.members.length}개 저장`
            : j.files[0]
              ? sizeLabel(j.files[0].size)
              : names[j.platform]}
        </span>
      </div>
    </article>
  );
}
