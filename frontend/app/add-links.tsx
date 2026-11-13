"use client";
import { useEffect, useRef, useState } from "react";
import { Icon } from "./ui";
export default function AddLinks({
  busy,
  onClose,
  onRegister,
}: {
  busy: boolean;
  onClose: () => void;
  onRegister: (body: unknown) => Promise<
    | {
        added: string[];
        duplicates: unknown[];
        rejected: { url: string; reason: string }[];
      }
    | undefined
  >;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [urls, setUrls] = useState(""),
    [mode, setMode] = useState("video"),
    [outputFormat, setOutputFormat] = useState("mp4"),
    [collections, setCollections] = useState(false),
    [limit, setLimit] = useState(25),
    [error, setError] = useState("");
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  async function submit() {
    const list = urls.trim().split(/\s+/).filter(Boolean);
    if (list.length > 100) {
      setError(
        "한 번에 100개까지 등록할 수 있습니다. Instagram 저장 목록은 왼쪽 메뉴에서 가져오세요.",
      );
      return;
    }
    const r = await onRegister({
      urls: list,
      mode,
      collections,
      collection_limit: limit,
      output_format: outputFormat,
    });
    if (r) {
      if (r.rejected.length) {
        setUrls(r.rejected.map((v) => v.url).join("\n"));
        setError(r.rejected.map((v) => v.reason).join("\n"));
      } else onClose();
    } else
      setError(
        "등록하지 못했습니다. 연결 상태와 라이브러리 여유를 확인한 뒤 다시 시도하세요.",
      );
  }
  return (
    <dialog
      ref={ref}
      className="add-dialog"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
    >
      <div className="dialog-title">
        <div>
          <Icon name="link" />
          <h2>링크 추가</h2>
        </div>
        <button
          className="icon-button"
          aria-label="링크 추가 닫기"
          disabled={busy}
          onClick={onClose}
        >
          <Icon name="close" size={18} />
        </button>
      </div>
      <p>여러 링크를 붙여넣으세요. 제목과 썸네일을 먼저 확인합니다.</p>
      <label htmlFor="urls">
        게시물 URL <span>한 번에 최대 100개</span>
      </label>
      <textarea
        id="urls"
        autoFocus
        rows={6}
        placeholder={
          "https://www.instagram.com/reel/…\nhttps://www.youtube.com/watch?v=…"
        }
        value={urls}
        onChange={(e) => setUrls(e.target.value)}
      />
      <div className="format-switch">
        <button
          className={mode === "video" ? "chosen" : ""}
          onClick={() => setMode("video")}
        >
          <Icon name="video" size={16} />
          미디어 자동 구분
        </button>
        <button
          className={mode === "audio" ? "chosen" : ""}
          onClick={() => setMode("audio")}
        >
          <Icon name="music" size={16} />
          오디오만
        </button>
      </div>
      {mode === "video" ? (
        <label className="output-choice">
          저장 형식
          <select
            value={outputFormat}
            onChange={(e) => setOutputFormat(e.target.value)}
          >
            <option value="mp4">MP4 · 기본</option>
            <option value="original">원본 형식 · 재인코딩 없음</option>
          </select>
        </label>
      ) : null}
      <div className="quality-line">
        <Icon name="check" size={15} />
        최고 화질 기본 · 링크 확인 후 해상도 선택 가능
      </div>
      <details className="collection-options">
        <summary>YouTube 재생목록·채널 옵션</summary>
        <label className="check-label">
          <input
            type="checkbox"
            checked={collections}
            onChange={(e) => setCollections(e.target.checked)}
          />
          재생목록·채널 가져오기
        </label>
        <label>
          최대{" "}
          <input
            type="number"
            min={1}
            max={100}
            value={limit}
            onChange={(e) =>
              setLimit(Math.min(100, Math.max(1, Number(e.target.value) || 1)))
            }
          />
          개
        </label>
        <p>
          영상 링크는 해당 영상만, 재생목록·채널 링크는 설정 개수까지
          등록합니다.
        </p>
      </details>
      {error ? (
        <div className="alert error" role="alert">
          {error}
        </div>
      ) : null}
      <div className="dialog-footer">
        <button className="button" disabled={busy} onClick={onClose}>
          취소
        </button>
        <button
          className="button primary"
          disabled={busy || !urls.trim()}
          onClick={() => void submit()}
        >
          {busy ? "등록 중…" : "링크 확인하기"}
          <Icon name="arrow" size={16} />
        </button>
      </div>
    </dialog>
  );
}
