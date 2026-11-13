"use client";
import { useEffect, useState } from "react";
import {
  Icon,
  Status,
  Thumbnail,
  MediaJob,
  names,
  busyStates,
  sizeLabel,
  duration,
} from "./ui";

export default function Inspector({
  job: item,
  busy,
  onAction,
  onDelete,
  onPreferences,
  onBrowser,
}: {
  job: MediaJob | undefined;
  busy: boolean;
  onBrowser?: (job: MediaJob) => void;
  onPreferences: (
    job: MediaJob,
    options: { output_format?: string; height?: number | null },
  ) => void;
  onAction: (path: string, body?: unknown) => void;
  onDelete: (job: MediaJob) => void;
}) {
  const [tab, setTab] = useState("properties");
  const [mediaFailed, setMediaFailed] = useState(false);
  const [memberId, setMemberId] = useState<string | null>(null);
  const members = item?.members;
  const job =
    members?.find((j) => j.id === memberId) ||
    (item?.status === "failed"
      ? members?.find((j) => j.status === "failed")
      : undefined) ||
    members?.find((j) => j.status === "completed") ||
    members?.[0] ||
    item;
  const memberIndex = members?.findIndex((j) => j.id === job?.id) ?? 0;
  const allFiles = members ? item?.files || [] : job?.files || [];
  useEffect(() => setMediaFailed(false), [job?.id]);
  if (!job)
    return (
      <aside className="inspector">
        <div className="inspector-tabs">
          <strong>속성</strong>
        </div>
        <div className="inspector-empty">
          <Icon name="video" size={28} />
          <p>
            항목을 선택하면
            <br />
            미리보기와 파일 정보가 표시됩니다.
          </p>
        </div>
      </aside>
    );
  const file = job.files[0];
  const image = job.metadata.media_type === "image";
  const audio = job.mode === "audio" || job.metadata.media_type === "audio";
  const playable = file && /\.(mp4|webm|m4a|mp3|ogg)$/i.test(file.name);
  return (
    <aside className="inspector">
      <div className="inspector-tabs">
        {[
          ["properties", "속성"],
          ["files", "파일"],
        ].map(([id, label]) => (
          <button
            className={tab === id ? "active" : ""}
            onClick={() => setTab(id)}
            key={id}
          >
            {label}
            {id === "files" && allFiles.length ? (
              <span>{allFiles.length}</span>
            ) : null}
          </button>
        ))}
      </div>
      {members ? (
        <div className="album-navigation">
          <strong>{item?.display_caption}</strong>
          <p>
            {item?.completed_count || 0} / {members.length}개 저장 완료 · 같은
            링크의 이미지 묶음
          </p>
          <div>
            <button
              className="icon-button"
              aria-label="이전 이미지"
              disabled={memberIndex <= 0}
              onClick={() => setMemberId(members[memberIndex - 1].id)}
            >
              ‹
            </button>
            <select
              aria-label="묶음 안의 미디어"
              value={job.id}
              onChange={(e) => setMemberId(e.target.value)}
            >
              {members.map((m, i) => (
                <option key={m.id} value={m.id}>
                  {i + 1} / {members.length} ·{" "}
                  {m.metadata.media_type === "image"
                    ? "이미지"
                    : "종류 확인 중"}{" "}
                  ·{" "}
                  {m.status === "completed"
                    ? "저장 완료"
                    : m.status === "failed"
                      ? "실패"
                      : "처리 중"}
                </option>
              ))}
            </select>
            <button
              className="icon-button"
              aria-label="다음 이미지"
              disabled={memberIndex >= members.length - 1}
              onClick={() => setMemberId(members[memberIndex + 1].id)}
            >
              ›
            </button>
          </div>
        </div>
      ) : null}
      <div className="inspector-scroll">
        <div className="inspector-preview">
          {image && file ? (
            <img
              src={`/api/files/${file.id}`}
              alt={job.metadata.title || "저장한 이미지"}
            />
          ) : playable && !mediaFailed ? (
            audio ? (
              <audio
                controls
                src={`/api/files/${file.id}`}
                preload="none"
                onError={() => setMediaFailed(true)}
              />
            ) : (
              <video
                key={job.id}
                controls
                playsInline
                preload="none"
                poster={job.metadata.thumbnail}
                src={`/api/files/${file.id}`}
                onError={() => setMediaFailed(true)}
              />
            )
          ) : (
            <Thumbnail job={job} />
          )}
        </div>
        {file && !image && (!playable || mediaFailed) ? (
          <p className="preview-hint">
            이 원본 형식은 브라우저에서 재생되지 않을 수 있습니다. 파일을 받거나
            MP4 호환본을 만드세요.
          </p>
        ) : null}
        <div className="inspector-heading">
          <span className="overline">{names[job.platform]}</span>
          <h2>{job.metadata.title || "미디어 확인 중"}</h2>
          <Status job={job} />
        </div>
        {tab === "properties" ? (
          <>
            {job.status === "ready" &&
            job.mode === "video" &&
            !image &&
            !audio ? (
              <section className="property-section download-options">
                <h3>다운로드 설정</h3>
                <label>
                  저장 형식
                  <select
                    aria-label="영상 저장 형식"
                    disabled={busy}
                    value={job.options?.output_format || "mp4"}
                    onChange={(e) =>
                      onPreferences(job, { output_format: e.target.value })
                    }
                  >
                    <option value="mp4">MP4 · 기본</option>
                    <option value="original">원본 형식</option>
                  </select>
                </label>
                <label>
                  해상도
                  <select
                    aria-label="다운로드 해상도"
                    disabled={busy}
                    value={job.options?.height || "best"}
                    onChange={(e) =>
                      onPreferences(job, {
                        height:
                          e.target.value === "best"
                            ? null
                            : Number(e.target.value),
                      })
                    }
                  >
                    <option value="best">최고 화질</option>
                    {(job.metadata.available_heights || []).map((h) => (
                      <option value={h} key={h}>
                        {h}p
                        {h === 2160
                          ? " · 4K"
                          : h === 1440
                            ? " · QHD"
                            : h === 1080
                              ? " · Full HD"
                              : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <p>
                  이 영상에서 확인된 화질만 표시합니다. MP4는 선택한 해상도를
                  유지하며 필요할 때 H.264/AAC로 변환합니다.
                </p>
              </section>
            ) : null}
            <section className="property-section">
              <h3>미디어 정보</h3>
              <dl>
                <div>
                  <dt>작성자</dt>
                  <dd>{job.metadata.uploader || "—"}</dd>
                </div>
                <div>
                  <dt>해상도</dt>
                  <dd>
                    {job.metadata.width && job.metadata.height
                      ? `${job.metadata.width} × ${job.metadata.height}`
                      : job.metadata.max_height
                        ? `${job.metadata.max_height}p`
                        : "—"}
                  </dd>
                </div>
                <div>
                  <dt>길이</dt>
                  <dd>{duration(job.metadata.duration)}</dd>
                </div>
                <div>
                  <dt>형식</dt>
                  <dd>
                    {image
                      ? "이미지 · 원본"
                      : audio
                        ? "오디오"
                        : file
                          ? file.name.split(".").pop()?.toUpperCase()
                          : "영상 + 오디오"}
                  </dd>
                </div>
                <div>
                  <dt>파일 크기</dt>
                  <dd>
                    {file
                      ? sizeLabel(job.files.reduce((n, f) => n + f.size, 0))
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>등록일</dt>
                  <dd>
                    {new Date(job.created_at * 1000).toLocaleDateString(
                      "ko-KR",
                    )}
                  </dd>
                </div>
                <div>
                  <dt>자동 삭제</dt>
                  <dd>
                    {job.expires_at
                      ? new Date(job.expires_at * 1000).toLocaleDateString(
                          "ko-KR",
                        )
                      : "안 함"}
                  </dd>
                </div>
              </dl>
            </section>
            {job.url ? (
              <section className="property-section">
                <h3>출처</h3>
                <a
                  className="source-link"
                  href={job.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span>{job.url}</span>
                  <Icon name="external" size={14} />
                </a>
              </section>
            ) : null}
            {job.error_message ? (
              <div className="inspector-error">
                <Icon name="info" size={18} />
                <div>
                  <strong>{job.error_code}</strong>
                  <p>{job.error_message}</p>
                </div>
              </div>
            ) : job.note ? (
              <p className="inspector-note">{job.note}</p>
            ) : null}
          </>
        ) : (
          <section className="property-section file-section">
            <h3>저장된 파일</h3>
            {allFiles.length ? (
              allFiles.map((f) => (
                <a href={`/api/files/${f.id}`} className="file-row" key={f.id}>
                  <Icon name="file" />
                  <span>
                    <strong>{f.name}</strong>
                    <small>{sizeLabel(f.size)}</small>
                  </span>
                  <Icon name="download" size={17} />
                </a>
              ))
            ) : (
              <p className="field-help">
                다운로드가 완료되면 여기에 파일이 표시됩니다.
              </p>
            )}
          </section>
        )}
      </div>
      <div className="inspector-actions">
        {onBrowser && job.platform === "instagram" ? (
          <button
            className="button full"
            disabled={busy}
            onClick={() => onBrowser(job)}
          >
            <Icon name="external" size={15} />
            Instagram에서 열어 저장
          </button>
        ) : null}
        {job.status === "completed" && file ? (
          <a className="button primary full" href={`/api/files/${file.id}`}>
            <Icon name="download" size={16} />
            다른 위치에 저장
          </a>
        ) : job.status === "ready" ? (
          <button
            className="button primary full"
            disabled={busy}
            onClick={() => onAction("jobs/start", { ids: [job.id] })}
          >
            <Icon name="download" size={16} />
            다운로드 시작
          </button>
        ) : job.status === "failed" && job.retryable ? (
          <button
            className="button full"
            disabled={busy}
            onClick={() => onAction("jobs/retry", { ids: [job.id] })}
          >
            <Icon name="refresh" size={16} />
            다시 시도
          </button>
        ) : null}
        {job.status === "completed" &&
        job.mode === "video" &&
        !image &&
        !audio &&
        job.platform !== "recording" ? (
          <button
            className="button full"
            disabled={busy}
            onClick={() => onAction(`jobs/${job.id}/compatible`)}
          >
            MP4 호환본 만들기<span className="subtle">720p</span>
          </button>
        ) : null}
        {!busyStates.has(job.status) ? (
          <button
            className="text-button danger"
            disabled={busy}
            onClick={() => onDelete(job)}
          >
            <Icon name="trash" size={14} />
            {members ? "현재 이미지와 기록 삭제" : "항목과 파일 삭제"}
          </button>
        ) : null}
      </div>
    </aside>
  );
}
