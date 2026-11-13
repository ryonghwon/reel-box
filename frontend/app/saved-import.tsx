"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "./api-client";
import { Icon } from "./ui";
type Preview = {
  draft_id: string;
  urls: string[];
  duplicates: number;
  ignored: number;
  files: string[];
  already_registered: number;
  available_slots: number;
  job_limit: number;
};
export default function SavedImport({
  onUpdate,
  onLibrary,
}: {
  onUpdate: () => void;
  onLibrary: () => void;
}) {
  const [preview, setPreview] = useState<Preview | null>(null),
    [filename, setFilename] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false),
    [auto, setAuto] = useState(true),
    [cursor, setCursor] = useState(0),
    [added, setAdded] = useState(0),
    [duplicates, setDuplicates] = useState(0),
    [status, setStatus] = useState("");
  const stop = useRef(false);
  const reading = useRef(false);
  useEffect(() => {
    let active = true;
    void api("imports/instagram-saved/draft")
      .then(({ draft }) => {
        if (!active || !draft || reading.current) return;
        setPreview(draft.preview);
        setFilename(draft.filename);
        setCursor(draft.cursor);
        setAdded(draft.added);
        setDuplicates(draft.duplicates);
        setAuto(draft.auto);
        setStatus(
          draft.cursor < draft.preview.urls.length
            ? "이전에 가져온 목록을 복원했습니다. 이어서 등록할 수 있습니다."
            : "등록한 목록입니다. 처리 결과는 라이브러리에서 확인하세요.",
        );
      })
      .catch(() => {});
    return () => {
      active = false;
      stop.current = true;
    };
  }, []);
  async function read(file?: File) {
    if (!file) return;
    reading.current = true;
    setError("");
    setPreview(null);
    setCursor(0);
    setAdded(0);
    setDuplicates(0);
    setStatus("");
    setFilename(file.name);
    if (file.size > 32 * 1024 ** 2) {
      setError(
        "32MB 이하 파일을 선택하세요. 큰 ZIP은 압축을 풀고 saved_posts.json 또는 HTML만 가져오세요.",
      );
      return;
    }
    setLoading(true);
    try {
      const r = await fetch(
        `/api/imports/instagram-saved?filename=${encodeURIComponent(file.name)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/octet-stream" },
          body: file,
        },
      );
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "파일을 읽을 수 없습니다.");
      setPreview(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  async function register() {
    if (!preview) return;
    setBusy(true);
    setError("");
    stop.current = false;
    let position = cursor;
    let totalAdded = added;
    let totalDuplicates = duplicates;
    try {
      await api("imports/instagram-saved/draft", "PUT", {
        draft_id: preview.draft_id,
        cursor: position,
        added: totalAdded,
        duplicates: totalDuplicates,
        auto,
      });
      while (position < preview.urls.length && !stop.current) {
        const count = 100;
        const batch = preview.urls.slice(position, position + count);
        const result = await api("jobs", "POST", {
          urls: batch,
          mode: "video",
          auto_download: auto,
          source: "instagram_saved",
        });
        if (result.rejected.length)
          throw new Error(
            "일부 링크를 등록할 수 없습니다. 남은 링크를 저장해 확인하세요.",
          );
        position += batch.length;
        totalAdded += result.added.length;
        totalDuplicates += result.duplicates.length;
        setCursor(position);
        setAdded(totalAdded);
        setDuplicates(totalDuplicates);
        await api("imports/instagram-saved/draft", "PUT", {
          draft_id: preview.draft_id,
          cursor: position,
          added: totalAdded,
          duplicates: totalDuplicates,
          auto,
        });
        onUpdate();
      }
      setStatus(
        position === preview.urls.length
          ? "목록 등록이 끝났습니다. 항목별 다운로드 결과는 라이브러리에서 확인하세요."
          : "등록을 일시 중지했습니다. 이미 등록한 작업은 계속 진행됩니다.",
      );
    } catch (e) {
      setError((e as Error).message);
      setStatus("아래에서 남은 링크를 저장하거나 등록을 이어갈 수 있습니다.");
    } finally {
      setBusy(false);
      onUpdate();
    }
  }
  async function clearList(confirm = true) {
    if (
      confirm &&
      !window.confirm(
        "가져온 링크 목록과 등록 진행 상태를 비울까요? 라이브러리에 등록한 작업과 파일은 유지됩니다.",
      )
    )
      return;
    try {
      await api("imports/instagram-saved/draft", "DELETE");
      setPreview(null);
      setFilename("");
      setCursor(0);
      setAdded(0);
      setDuplicates(0);
      setStatus("");
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function saveRemaining() {
    if (!preview) return;
    const url = URL.createObjectURL(
      new Blob([preview.urls.slice(cursor).join("\n")], {
        type: "text/plain;charset=utf-8",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "instagram-saved-remaining.txt";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const complete =
    !!preview &&
    preview.urls.length > 0 &&
    cursor >= preview.urls.length &&
    !busy;
  if (complete)
    return (
      <section className="saved-view">
        <div className="utility-heading">
          <h1>Instagram 저장 목록</h1>
          <p>가져온 게시물의 다운로드는 라이브러리에서 계속 진행됩니다.</p>
        </div>
        <section className="panel import-complete">
          <div className="complete-icon">
            <Icon name="check" size={24} />
          </div>
          <h2>가져오기 완료</h2>
          <p className="complete-count">
            {added.toLocaleString()}개 등록
            {duplicates ? ` · 중복 ${duplicates.toLocaleString()}개 제외` : ""}
          </p>
          <p className="complete-filename" title={filename}>
            {filename}
          </p>
          <div className="import-actions">
            <button className="button primary" onClick={onLibrary}>
              라이브러리 열기
              <Icon name="arrow" size={16} />
            </button>
            <button className="button" onClick={() => void clearList(false)}>
              다른 파일 가져오기
            </button>
          </div>
          <p className="field-help">
            등록한 게시물과 다운로드한 파일은 그대로 유지됩니다.
          </p>
          {error ? (
            <div className="alert error" role="alert">
              {error}
            </div>
          ) : null}
        </section>
      </section>
    );
  return (
    <section className="saved-view">
      <div className="view-title">
        <div className="view-symbol">
          <Icon name="bookmark" size={26} />
        </div>
        <h1>Instagram 저장 목록</h1>
        <p>저장해 둔 게시물을 한 번에 가져오세요.</p>
      </div>
      <div className="saved-layout">
        <div>
          <section className="panel import-panel">
            <div className="section-top">
              <h2>저장 목록 가져오기</h2>
              <span className="subtle">ZIP · JSON · HTML</span>
            </div>
            <label className={`drop-zone ${loading ? "loading" : ""}`}>
              <Icon name="upload" size={30} />
              <strong>
                {loading
                  ? "저장 목록을 읽는 중…"
                  : "Instagram 내보내기 파일 선택"}
              </strong>
              <span>
                {filename || "ZIP 그대로, 또는 saved_posts 파일을 선택하세요"}
              </span>
              <span className="button">파일 찾아보기</span>
              <input
                type="file"
                aria-label="Instagram 저장 목록 파일"
                accept=".zip,.json,.html,.htm"
                disabled={loading || busy}
                onChange={(e) => {
                  void read(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
            </label>
            <p className="field-help">
              최대 32MB. 선택한 파일은 내 컴퓨터에서 읽고, 저장 목록 링크만
              작업에 사용합니다. 원본 내보내기 파일은 보관하지 않으며, 링크와
              등록 진행 상태만 내 컴퓨터에 저장해 이어서 처리합니다.
            </p>
            {error ? (
              <div className="alert error" role="alert">
                <Icon name="info" />
                <span>{error}</span>
              </div>
            ) : null}
            {preview ? (
              <div className="import-preview">
                <div className="import-count">
                  <strong>{preview.urls.length.toLocaleString()}</strong>
                  <span>개 게시물</span>
                  <span className="pill">
                    파일 안 중복 {preview.duplicates}개 제외
                  </span>
                </div>
                <div className="import-detail">
                  <span>
                    이미 라이브러리에 있는 링크{" "}
                    <b>{preview.already_registered}개</b>
                  </span>
                  <span>
                    읽은 파일 <b>{preview.files.join(", ")}</b>
                  </span>
                  <span>
                    게시물이 아닌 링크 <b>{preview.ignored}개 제외</b>
                  </span>
                </div>
                <details>
                  <summary>가져올 링크 미리보기</summary>
                  <div className="url-preview">
                    {preview.urls.slice(0, 12).map((url) => (
                      <a href={url} target="_blank" rel="noreferrer" key={url}>
                        {url}
                        <Icon name="external" size={12} />
                      </a>
                    ))}
                    {preview.urls.length > 12 ? (
                      <span>외 {preview.urls.length - 12}개</span>
                    ) : null}
                  </div>
                </details>
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={auto}
                    disabled={busy || cursor > 0}
                    onChange={(e) => setAuto(e.target.checked)}
                  />
                  <span>
                    가져온 미디어 자동 다운로드
                    <small>
                      해제하면 미리보기 확인 후 라이브러리에서 다운로드를
                      시작합니다.
                    </small>
                  </span>
                </label>
                <div className="info-box">
                  <Icon name="info" size={17} />
                  <p>
                    영상과 이미지를 자동으로 구분해 저장합니다. 삭제·로그인
                    제한은 해당 작업에 이유가 표시됩니다. 라이브러리은 최대{" "}
                    {preview.job_limit.toLocaleString()}개 작업을 유지하며,
                    등록할 때 최신 라이브러리 여유를 확인합니다. 캐러셀 영상은
                    작업이 더 늘어날 수 있습니다.
                  </p>
                </div>
                {cursor > 0 ? (
                  <div className="import-progress">
                    <div>
                      <span>
                        {cursor.toLocaleString()} /{" "}
                        {preview.urls.length.toLocaleString()}개 처리
                      </span>
                      <span>
                        등록 {added} · 기존 중복 {duplicates}
                      </span>
                    </div>
                    <progress max={preview.urls.length} value={cursor} />
                  </div>
                ) : null}
                <div className="import-actions">
                  {busy ? (
                    <button
                      className="button"
                      onClick={() => {
                        stop.current = true;
                      }}
                    >
                      가져오기 일시 중지
                    </button>
                  ) : (
                    <button
                      className="button primary"
                      disabled={cursor === preview.urls.length}
                      onClick={() => void register()}
                    >
                      <Icon name="download" size={16} />
                      {cursor === preview.urls.length
                        ? "등록 완료"
                        : cursor
                          ? "이어서 가져오기"
                          : auto
                            ? "가져오기 및 다운로드"
                            : "목록 가져오기"}
                    </button>
                  )}
                  {cursor > 0 ? (
                    <button className="button" onClick={onLibrary}>
                      라이브러리 열기
                      <Icon name="arrow" size={15} />
                    </button>
                  ) : null}
                  {cursor < preview.urls.length ? (
                    <button className="text-button" onClick={saveRemaining}>
                      남은 링크 저장
                    </button>
                  ) : null}
                  <button
                    className="text-button danger"
                    disabled={busy}
                    onClick={() => void clearList()}
                  >
                    가져오기 취소
                  </button>
                </div>
                {status ? (
                  <p className="field-help" role="status">
                    {status}
                  </p>
                ) : null}
              </div>
            ) : null}
          </section>
          <div className="saved-note">
            <Icon name="bookmark" />
            <div>
              <strong>저장 목록에는 게시물 주소가 들어 있습니다.</strong>
              <p>
                내보내기 파일에서 게시물 주소를 읽은 다음 각 사이트에서 미디어
                파일을 다운로드합니다. 로그인만 연결해 모든 저장 영상을 가져오는
                기능은 현재 제공하지 않습니다.
              </p>
            </div>
          </div>
        </div>
        <aside className="export-guide">
          <span className="eyebrow">가져오기 안내</span>
          <h2>
            Instagram에서
            <br />
            저장 목록 내보내기
          </h2>
          <ol>
            <li>
              <strong>계정 센터 열기</strong>
              <p>
                Instagram 설정에서 계정 센터 → 내 정보 및 권한으로 이동하세요.
              </p>
            </li>
            <li>
              <strong>저장됨 항목 선택</strong>
              <p>
                내 정보 내보내기(또는 다운로드) → 기기로 내보내기에서 해당
                계정의 저장됨(Saved)을 선택하세요.
              </p>
            </li>
            <li>
              <strong>전체 기간 · JSON</strong>
              <p>
                기간을 전체로 지정하고 내보내기를 요청하세요. 준비 시간은
                Instagram에 따라 달라집니다.
              </p>
            </li>
            <li>
              <strong>파일 가져오기</strong>
              <p>
                완료 알림을 받은 뒤 파일을 내려받아 왼쪽에서 선택하세요. 메뉴
                이름과 파일 구조는 계정에 따라 다를 수 있습니다.
              </p>
            </li>
          </ol>
          <a
            className="button"
            href="https://accountscenter.instagram.com/info_and_permissions/"
            target="_blank"
            rel="noreferrer"
          >
            Instagram 계정 센터
            <Icon name="external" size={14} />
          </a>
          <a
            className="text-button"
            href="https://help.instagram.com/181231772500920"
            target="_blank"
            rel="noreferrer"
          >
            Instagram 공식 도움말
            <Icon name="external" size={13} />
          </a>
        </aside>
      </div>
    </section>
  );
}
