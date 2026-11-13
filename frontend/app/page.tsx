"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { buildLibrary, expandSelection } from "./library";
import Recorder from "./recorder";
import PlatformIcon from "./platform-icon";
import BrandMark from "./brand-mark";
import StorageSettings from "./storage-settings";
import PlatformGuide from "./platform-guide";
import AddLinks from "./add-links";
import Inspector from "./inspector";
import SavedImport from "./saved-import";
import {
  api,
  Icon,
  Status,
  Thumbnail,
  MediaJob,
  Settings,
  Health,
  names,
  busyStates,
  sizeLabel,
} from "./ui";

export default function Home() {
  const [view, setView] = useState("library"),
    [jobs, setJobs] = useState<MediaJob[]>([]),
    [settings, setSettings] = useState<Settings | null>(null),
    [health, setHealth] = useState<Health | null>(null),
    [filter, setFilter] = useState("all"),
    [savedOnly, setSavedOnly] = useState(false),
    [platform, setPlatform] = useState("all"),
    [query, setQuery] = useState(""),
    [selected, setSelected] = useState<Set<string>>(new Set()),
    [focus, setFocus] = useState<string | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [loaded, setLoaded] = useState(false),
    [adding, setAdding] = useState(false),
    [layout, setLayout] = useState("grid"),
    [visibleCount, setVisibleCount] = useState(48);
  const search = useRef<HTMLInputElement>(null);
  const [desktopInfo, setDesktopInfo] = useState<{
    platform: string;
    version: string;
    storageRoot: string;
  } | null>(null);
  useEffect(() => {
    void window.reelboxDesktop
      ?.getInfo()
      .then((info) => {
        setDesktopInfo(info);
        if (info.layout && ["grid", "compact", "list"].includes(info.layout))
          setLayout(info.layout);
      })
      .catch(() => {});
    try {
      const saved = localStorage.getItem("reelbox.layout.v1");
      if (saved && ["grid", "compact", "list"].includes(saved))
        setLayout(saved);
    } catch {}
  }, []);
  function chooseLayout(value: string) {
    setLayout(value);
    void window.reelboxDesktop
      ?.setLayout(value)
      .catch(() => setError("보기 설정을 저장하지 못했습니다."));
    try {
      localStorage.setItem("reelbox.layout.v1", value);
    } catch {}
  }
  const syncTime = useRef(0);
  const pendingRefresh = useRef<Promise<void> | null>(null);
  const scrollRoot = useRef<HTMLDivElement>(null);
  const libraryMain = useRef<HTMLElement>(null);
  const loadMore = useRef<HTMLDivElement>(null);
  // Scroll changes only one CSS variable; thousands of media cards do not rerender.
  useEffect(() => {
    const canvas = scrollRoot.current,
      main = libraryMain.current;
    if (view !== "library" || !canvas || !main) return;
    let frame = 0;
    const paint = () => {
      frame = 0;
      main.style.setProperty(
        "--header-collapse",
        String(Math.min(1, Math.max(0, canvas.scrollTop) / 240)),
      );
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(paint);
    };
    canvas.addEventListener("scroll", schedule, { passive: true });
    paint();
    return () => {
      canvas.removeEventListener("scroll", schedule);
      cancelAnimationFrame(frame);
    };
  }, [view]);
  const refresh = useCallback(() => {
    if (pendingRefresh.current) return pendingRefresh.current;
    const task = (async () => {
      const since = syncTime.current;
      const [j, h] = await Promise.all([
        api("jobs" + (since ? "?since=" + since : "")),
        api("health"),
      ]);
      setJobs((previous) => {
        if (!since) return j.jobs;
        const live = new Set<string>(j.all_ids);
        const merged = new Map(
          previous
            .filter((item) => live.has(item.id))
            .map((item) => [item.id, item]),
        );
        for (const item of j.jobs as MediaJob[]) merged.set(item.id, item);
        return Array.from(merged.values()).sort(
          (a, b) => b.created_at - a.created_at,
        );
      });
      syncTime.current = j.server_time;
      setHealth(h);
      setLoaded(true);
    })();
    pendingRefresh.current = task;
    void task
      .finally(() => {
        pendingRefresh.current = null;
      })
      .catch(() => {});
    return task;
  }, []);
  const updated = useCallback(() => {
    void refresh().catch((e) => setError(e.message));
  }, [refresh]);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        await refresh();
      } catch {
        if (!stopped) setHealth(null);
      } finally {
        if (!stopped) timer = setTimeout(poll, document.hidden ? 10000 : 2500);
      }
    }
    void poll();
    void api("settings")
      .then((v) => {
        if (!stopped) setSettings(v);
      })
      .catch(() => {});
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [refresh]);
  useEffect(() => {
    function shortcut(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setAdding(true);
      }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);
  const libraryItems = useMemo(() => buildLibrary(jobs), [jobs]);
  const completed = jobs.filter((j) => j.status === "completed"),
    ready = jobs.filter((j) => j.status === "ready"),
    failed = libraryItems.filter((j) => j.status === "failed");
  const originalLinks = new Set(
    jobs
      .filter(
        (j) =>
          !j.parent_id &&
          j.url &&
          (platform === "all" || j.platform === platform) &&
          (!savedOnly || j.options?.source === "instagram_saved"),
      )
      .map((j) => j.platform + ":" + j.url),
  ).size;
  const baseJobs = libraryItems.filter(
    (j) =>
      (!savedOnly || j.options?.source === "instagram_saved") &&
      (platform === "all" || j.platform === platform) &&
      `${j.metadata.title || ""} ${j.metadata.uploader || ""} ${j.url} ${names[j.platform]}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const albumCount = baseJobs.filter((j) => (j.image_count || 0) > 0).length;
  const videoCount = baseJobs.filter(
    (j) =>
      !j.members && j.mode !== "audio" && j.metadata.media_type === "video",
  ).length;
  const audioCount = baseJobs.filter(
    (j) =>
      !j.members && (j.mode === "audio" || j.metadata.media_type === "audio"),
  ).length;
  const unresolvedCount =
    baseJobs.length - albumCount - videoCount - audioCount;
  const shown = baseJobs.filter(
    (j) =>
      filter === "all" ||
      (filter === "active" ? busyStates.has(j.status) : j.status === filter),
  );
  const paged = shown.slice(0, visibleCount);
  useEffect(() => {
    setVisibleCount(48);
    scrollRoot.current?.scrollTo({ top: 0 });
  }, [filter, platform, savedOnly, query, layout]);
  useEffect(() => {
    const node = loadMore.current;
    if (!node || view !== "library" || visibleCount >= shown.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting))
          setVisibleCount((n) => Math.min(n + 48, shown.length));
      },
      { rootMargin: "600px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [view, visibleCount, shown.length]);
  const focused =
    shown.find((j) => j.id === focus) ||
    shown.find((j) => j.status === "completed") ||
    shown[0];
  const scopeIds = new Set(selected.size ? selected : shown.map((j) => j.id));
  const scope = new Set(expandSelection(libraryItems, scopeIds));
  const targets = ready.filter((j) => scope.has(j.id));
  const retryable = jobs.filter(
    (j) => j.status === "failed" && j.retryable && scope.has(j.id),
  );
  const hasFiles = completed.some((j) => scope.has(j.id));
  const loginTargets = jobs.filter(
    (j) =>
      scope.has(j.id) &&
      j.platform === "instagram" &&
      j.status === "failed" &&
      j.mode === "video",
  );
  const infoTargets = jobs.filter(
    (j) =>
      scope.has(j.id) &&
      j.platform === "instagram" &&
      j.status === "completed" &&
      (j.options?.source === "browser" || j.options?.browser_import) &&
      (selected.size > 0 || j.metadata.browser_metadata_version !== 2),
  );
  async function action(path: string, body?: unknown) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api(path, "POST", body);
      await refresh();
      return result;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function exportFiles(name: string) {
    if (busy || !scope.size) return;
    setBusy(true);
    setError("");
    try {
      const result = await api("exports", "POST", { ids: Array.from(scope) });
      window.location.assign(`/api/${name}?selection=${result.selection}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function preferences(
    job: MediaJob,
    changes: { output_format?: string; height?: number | null },
  ) {
    setBusy(true);
    setError("");
    try {
      await api("jobs/" + job.id + "/preferences", "PUT", {
        output_format: job.options?.output_format || "mp4",
        height: job.options?.height || null,
        ...changes,
      });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove(job: MediaJob) {
    if (!window.confirm("이 작업 기록과 저장 파일을 삭제할까요?")) return;
    try {
      await api(`jobs/${job.id}`, "DELETE");
      setSelected((s) => {
        const n = new Set(s);
        n.delete(job.id);
        return n;
      });
      setFocus(null);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function removeSelection() {
    if (busy || !scope.size) return;
    if (
      !window.confirm(
        `${scopeIds.size.toLocaleString()}개 선택 항목에 포함된 미디어 ${scope.size.toLocaleString()}개의 기록과 파일을 삭제할까요? 처리 중인 항목은 제외합니다.`,
      )
    )
      return;
    const result = await action("jobs/delete", { ids: Array.from(scope) });
    if (result) {
      setSelected(new Set());
      setFocus(null);
      setNotice(
        `${result.deleted.length}개 삭제 · 처리 중 ${result.skipped.length}개 제외`,
      );
    }
  }
  const storagePath =
    settings?.download_directory ||
    [
      settings?.host_storage_root ||
        desktopInfo?.storageRoot ||
        settings?.storage_root ||
        "",
      settings?.folder || "Reelbox",
    ]
      .filter(Boolean)
      .join(desktopInfo?.platform === "win32" ? "\\" : "/");
  async function openBrowser(job: MediaJob) {
    try {
      await window.reelboxDesktop?.openBrowser(job.url, job.id);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function retryWithLogin() {
    try {
      await window.reelboxDesktop?.openBrowserBatch(
        loginTargets.slice(0, 500).map((j) => j.id),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function updateBrowserInfo() {
    try {
      await window.reelboxDesktop?.openBrowserBatch(
        infoTargets.slice(0, 500).map((j) => j.id),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function openStorage() {
    try {
      if (window.reelboxDesktop) {
        const error = await window.reelboxDesktop.openLibrary();
        if (error) throw Error(error);
      } else {
        await navigator.clipboard.writeText(storagePath);
        setNotice(
          "저장 경로를 복사했습니다. 탐색기 또는 Finder에서 열 수 있습니다.",
        );
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function toggle(id: string) {
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }
  function library(nextFilter = "all", nextPlatform = "all") {
    setView("library");
    setFilter(nextFilter === "saved" ? "all" : nextFilter);
    setSavedOnly(nextFilter === "saved");
    setPlatform(nextPlatform);
    setVisibleCount(48);
    setQuery("");
    setFocus(null);
  }
  const title =
    view === "library"
      ? platform === "all"
        ? "라이브러리"
        : names[platform]
      : view === "saved"
        ? "Instagram 저장 목록"
        : view === "record"
          ? "화면 녹화"
          : view === "settings"
            ? "저장 설정"
            : "플랫폼 안내";
  return (
    <div className="app-shell">
      <header className="app-bar">
        <a className="brand" href="/" aria-label="Reel Box 홈">
          <span className="brand-icon">
            <BrandMark size={22} />
          </span>
          <strong>Reel Box</strong>
          <span className="brand-version">{desktopInfo ? "APP" : "LOCAL"}</span>
        </a>
        <div className="breadcrumb">
          <span>내 컴퓨터</span>
          <Icon name="chevron" size={12} />
          <strong>{title}</strong>
        </div>
        <div className="top-actions">
          <span className="connection">
            <span
              className={`dot ${health?.queue && health.workers ? "green" : ""}`}
            />
            {health?.cooldowns?.length
              ? health.cooldowns
                  .map(
                    (c) =>
                      `${names[c.platform] || c.platform} ${new Date(c.until * 1000).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false })} 재개`,
                  )
                  .join(" · ")
              : health?.queue && health.workers
                ? `동시 ${health.workers}개 처리`
                : "연결 확인 중"}
          </span>
          <button
            className="button primary small"
            onClick={() => setAdding(true)}
          >
            <Icon name="plus" size={16} />
            링크 추가
          </button>
        </div>
      </header>
      <aside className="sidebar">
        <div className="workspace-name">
          <span className="workspace-avatar">R</span>
          <div>
            <strong>개인 라이브러리</strong>
            <span>내 컴퓨터</span>
          </div>
        </div>
        <nav aria-label="라이브러리 메뉴">
          <div className="nav-section-label">작업 공간</div>
          <button
            className={`nav-item ${view === "library" && platform === "all" && !savedOnly ? "active" : ""}`}
            onClick={() => library()}
          >
            <Icon name="grid" size={17} />
            라이브러리<span>{libraryItems.length}</span>
          </button>
          <button
            className={`nav-item ${view === "saved" ? "active" : ""}`}
            onClick={() => setView("saved")}
          >
            <Icon name="bookmark" size={17} />
            Instagram 저장 목록
          </button>
          <button
            className={`nav-item ${view === "record" ? "active" : ""}`}
            onClick={() => setView("record")}
          >
            <Icon name="video" size={17} />
            화면 녹화
          </button>
          <div className="nav-section-label">플랫폼</div>
          {Object.entries(names)
            .filter(([k]) => k !== "recording")
            .map(([id, name]) => (
              <button
                key={id}
                className={`nav-item platform-nav ${view === "library" && platform === id ? "active" : ""}`}
                onClick={() => library("all", id)}
              >
                <PlatformIcon platform={id} />
                {name}
                <span>
                  {libraryItems.filter((j) => j.platform === id).length || ""}
                </span>
              </button>
            ))}
          <div className="nav-section-label">모아 보기</div>
          <button
            className={`nav-item ${view === "library" && savedOnly ? "active" : ""}`}
            onClick={() => library("saved")}
          >
            <Icon name="bookmark" size={16} />
            가져온 게시물
          </button>
          <button className="nav-item" onClick={() => library("failed")}>
            <Icon name="info" size={16} />
            실패한 항목
            <span className={failed.length ? "attention-count" : ""}>
              {failed.length || ""}
            </span>
          </button>
        </nav>
        <div className="sidebar-bottom">
          <button
            className={`nav-item ${view === "settings" ? "active" : ""}`}
            onClick={() => setView("settings")}
          >
            <Icon name="settings" size={17} />
            저장 설정
          </button>
          <button
            className={`nav-item ${view === "support" ? "active" : ""}`}
            onClick={() => setView("support")}
          >
            <Icon name="info" size={17} />
            플랫폼 안내
          </button>
          <div className="storage-shortcut">
            <button
              className="storage-card"
              title={storagePath}
              onClick={() => void openStorage()}
            >
              <Icon name="folder" size={16} />
              <div>
                <strong>
                  {desktopInfo ? "저장 폴더 열기" : "저장 경로 복사"}
                </strong>
                <span>
                  {health
                    ? `${sizeLabel(health.free_bytes)} 사용 가능`
                    : "내 컴퓨터에 저장"}
                </span>
              </div>
              <Icon name="external" size={12} />
            </button>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <div className="notifications">
          {error ? (
            <div className="alert error" role="alert">
              <Icon name="info" size={17} />
              <span>{error}</span>
              <button
                className="icon-button"
                onClick={() => setError("")}
                aria-label="오류 닫기"
              >
                <Icon name="close" size={15} />
              </button>
            </div>
          ) : null}
          {notice ? (
            <div className="alert notice" role="status">
              <Icon name="check" size={17} />
              <span>{notice}</span>
              <button
                className="icon-button"
                onClick={() => setNotice("")}
                aria-label="알림 닫기"
              >
                <Icon name="close" size={15} />
              </button>
            </div>
          ) : null}
        </div>
        {view === "library" ? (
          <div className="library-workspace">
            <main className="library-main" ref={libraryMain}>
              <div className="library-heading">
                <div>
                  <div className="overline">LIBRARY</div>
                  <h1>
                    {savedOnly ? "가져온 게시물" : title}
                    <span>{shown.length}항목</span>
                  </h1>
                  <p className="library-counts">
                    원본 링크 {originalLinks.toLocaleString()}개 · 영상{" "}
                    {videoCount.toLocaleString()}개 · 이미지{" "}
                    {albumCount.toLocaleString()}묶음
                    {audioCount ? ` · 오디오 ${audioCount}개` : ""}
                    {unresolvedCount
                      ? ` · 확인 대기 ${unresolvedCount}항목`
                      : ""}
                  </p>
                </div>
                <div className="layout-switch">
                  <button
                    aria-label="그리드 보기"
                    aria-pressed={layout === "grid"}
                    className={layout === "grid" ? "active" : ""}
                    title="카드 보기"
                    onClick={() => chooseLayout("grid")}
                  >
                    <Icon name="grid" size={16} />
                  </button>
                  <button
                    aria-label="작은 썸네일 보기"
                    title="작은 썸네일 보기"
                    aria-pressed={layout === "compact"}
                    className={layout === "compact" ? "active" : ""}
                    onClick={() => chooseLayout("compact")}
                  >
                    <Icon name="compact" size={17} />
                  </button>
                  <button
                    aria-label="목록 보기"
                    aria-pressed={layout === "list"}
                    className={layout === "list" ? "active" : ""}
                    title="목록 보기"
                    onClick={() => chooseLayout("list")}
                  >
                    <Icon name="list" size={18} />
                  </button>
                </div>
              </div>
              <div className="library-toolbar">
                <div className="search-wrap">
                  <Icon name="search" size={16} />
                  <input
                    ref={search}
                    aria-label="제목·작성자·링크 검색"
                    placeholder="제목·작성자·링크 검색"
                    value={query}
                    onChange={(e) => {
                      setQuery(e.target.value);
                      setVisibleCount(48);
                    }}
                  />
                </div>
                <button className="button" onClick={() => setView("saved")}>
                  <Icon name="bookmark" size={15} />
                  <span>저장 목록 가져오기</span>
                </button>
              </div>
              <div className="tabs" role="tablist" aria-label="작업 상태">
                {[
                  ["all", "전체", baseJobs.length],
                  [
                    "ready",
                    "다운로드 가능",
                    baseJobs.filter((j) => j.status === "ready").length,
                  ],
                  [
                    "active",
                    "진행 중",
                    baseJobs.filter((j) => busyStates.has(j.status)).length,
                  ],
                  [
                    "completed",
                    "완료",
                    baseJobs.filter((j) => j.status === "completed").length,
                  ],
                  [
                    "failed",
                    "실패",
                    baseJobs.filter((j) => j.status === "failed").length,
                  ],
                ].map(([id, label, count]) => (
                  <button
                    role="tab"
                    aria-selected={filter === id}
                    key={id}
                    onClick={() => {
                      setFilter(String(id));
                      setVisibleCount(48);
                      setFocus(null);
                    }}
                    className={filter === id ? "current" : ""}
                  >
                    {label}
                    <span>{count}</span>
                  </button>
                ))}
              </div>
              <div className="selection-toolbar">
                <label>
                  <input
                    type="checkbox"
                    aria-label="불러온 항목 모두 선택"
                    checked={
                      paged.length > 0 && paged.every((j) => selected.has(j.id))
                    }
                    onChange={(e) => {
                      const checked = e.target.checked;
                      setSelected((s) => {
                        const n = new Set(s);
                        paged.forEach((j) =>
                          checked ? n.add(j.id) : n.delete(j.id),
                        );
                        return n;
                      });
                    }}
                  />
                  <span>
                    {selected.size
                      ? `${selected.size}개 선택`
                      : "불러온 항목 선택"}
                  </span>
                </label>
                {selected.size ? (
                  <button
                    className="text-button"
                    onClick={() => setSelected(new Set())}
                  >
                    선택 해제
                  </button>
                ) : (
                  <span className="sort-label">최근 추가순</span>
                )}
                <div className="selection-actions">
                  {desktopInfo && infoTargets.length ? (
                    <button
                      className="button small"
                      disabled={busy}
                      onClick={() => void updateBrowserInfo()}
                    >
                      게시물 정보 갱신 {infoTargets.length}
                    </button>
                  ) : null}
                  {desktopInfo && loginTargets.length ? (
                    <button
                      className="button small"
                      disabled={busy}
                      onClick={() => void retryWithLogin()}
                    >
                      로그인 후 재시도 {loginTargets.length}
                    </button>
                  ) : null}
                  <button
                    className="text-button danger"
                    disabled={busy || !scope.size}
                    onClick={() => void removeSelection()}
                  >
                    <Icon name="trash" size={14} />
                    {selected.size ? "선택 삭제" : "목록 삭제"}
                  </button>
                  <button
                    className="text-button"
                    disabled={busy || !scope.size}
                    onClick={() => void exportFiles("manifest.csv")}
                    title={
                      selected.size ? "선택한 기록 CSV" : "검색·필터 결과 CSV"
                    }
                  >
                    CSV
                  </button>
                  <button
                    className="button small"
                    disabled={busy || !hasFiles}
                    onClick={() => void exportFiles("archive.zip")}
                  >
                    <Icon name="folder" size={14} />
                    {selected.size
                      ? "선택 항목 ZIP"
                      : filter === "all" &&
                          platform === "all" &&
                          !query &&
                          !savedOnly
                        ? "전체 ZIP 저장"
                        : "ZIP 저장"}
                  </button>
                  <button
                    className="button dark small"
                    disabled={busy || !targets.length}
                    onClick={async () => {
                      const r = await action("jobs/start", {
                        ids: targets.map((j) => j.id),
                      });
                      if (r)
                        setNotice(
                          `${r.updated.length}개 다운로드를 시작했습니다.`,
                        );
                    }}
                  >
                    <Icon name="download" size={14} />
                    {selected.size ? "선택 다운로드" : "다운로드 시작"}
                  </button>
                </div>
              </div>
              <div className="library-canvas" ref={scrollRoot}>
                {paged.length ? (
                  <div className={`media-${layout}`}>
                    {paged.map((j) => (
                      <article
                        key={j.id}
                        className={`media-card ${focused?.id === j.id ? "focused" : ""} ${selected.has(j.id) ? "selected" : ""}`}
                      >
                        <div className="card-image">
                          <button
                            className="preview-trigger"
                            aria-label={`${j.metadata.title || j.url} 상세 보기`}
                            onClick={() => setFocus(j.id)}
                          >
                            <Thumbnail job={j} />
                          </button>
                          <input
                            className="card-checkbox"
                            type="checkbox"
                            aria-label={`${j.metadata.title || j.url} 선택`}
                            checked={selected.has(j.id)}
                            onChange={() => toggle(j.id)}
                          />
                          <span className="media-format">
                            {j.members
                              ? j.image_count
                                ? `사진 ${j.image_count}장`
                                : "종류 확인 중"
                              : j.metadata.media_type === "image"
                                ? "IMAGE"
                                : j.mode === "audio" ||
                                    j.metadata.media_type === "audio"
                                  ? "AUDIO"
                                  : j.files[0]?.name
                                      .split(".")
                                      .pop()
                                      ?.toUpperCase() || "VIDEO"}
                          </span>
                        </div>
                        <button
                          className="card-copy"
                          onClick={() => setFocus(j.id)}
                        >
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
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">
                    <div className="empty-icon">
                      <Icon name="video" size={32} />
                    </div>
                    <h2>
                      {!loaded
                        ? "라이브러리를 불러오는 중"
                        : jobs.length
                          ? "일치하는 항목이 없습니다"
                          : "미디어를 추가하세요"}
                    </h2>
                    <p>
                      {jobs.length
                        ? "검색어나 상태 필터를 바꿔보세요."
                        : "링크를 붙여넣거나 Instagram 저장 목록을 가져오세요."}
                    </p>
                    <button
                      className="button primary"
                      onClick={() => setAdding(true)}
                    >
                      <Icon name="plus" size={16} />
                      링크 추가
                    </button>
                  </div>
                )}
                {paged.length < shown.length ? (
                  <div ref={loadMore} className="load-more">
                    <button
                      className="text-button"
                      onClick={() =>
                        setVisibleCount((n) => Math.min(n + 48, shown.length))
                      }
                    >
                      더 불러오기
                    </button>
                    <span>아래로 스크롤하면 계속 표시됩니다.</span>
                  </div>
                ) : shown.length ? (
                  <div className="load-more subtle">모두 불러왔습니다.</div>
                ) : null}
              </div>
              <footer className="library-footer">
                <span>
                  {shown.length
                    ? `${Math.min(visibleCount, shown.length).toLocaleString()} / ${shown.length.toLocaleString()}항목 표시`
                    : "0개"}
                  <span className="footer-divider">·</span>최고 화질
                </span>
                <div>
                  <button
                    className="text-button"
                    disabled={busy || !retryable.length}
                    onClick={() =>
                      void action("jobs/retry", {
                        ids: retryable.map((j) => j.id),
                      })
                    }
                  >
                    <Icon name="refresh" size={13} />
                    실패 재시도
                  </button>
                </div>
              </footer>
            </main>
            <Inspector
              job={focused}
              busy={busy}
              onBrowser={
                desktopInfo ? (job) => void openBrowser(job) : undefined
              }
              onAction={(path, body) => {
                void action(path, body);
              }}
              onDelete={(j) => void remove(j)}
              onPreferences={(j, opts) => void preferences(j, opts)}
            />
          </div>
        ) : null}
        <main className="utility-view" hidden={view !== "saved"}>
          <SavedImport onUpdate={updated} onLibrary={() => library("saved")} />
        </main>
        <main className="utility-view" hidden={view !== "record"}>
          <div className="utility-heading">
            <span className="overline">CAPTURE</span>
            <h1>화면 녹화</h1>
            <p>직접 선택한 탭이나 창을 영상 파일로 보관합니다.</p>
          </div>
          <Recorder
            onSaved={() => {
              updated();
              setNotice(
                "녹화 파일을 저장했습니다. 변환 후 라이브러리에서 확인하세요.",
              );
            }}
          />
        </main>
        {view === "settings" && settings ? (
          <StorageSettings
            settings={settings}
            storagePath={storagePath}
            desktop={!!desktopInfo}
            busy={busy}
            onChange={setSettings}
            onOpen={() => void openStorage()}
            onChoose={async () => {
              try {
                const result = await window.reelboxDesktop?.chooseLibrary();
                if (result) {
                  setSettings(result);
                  setNotice(
                    "저장 폴더를 변경했습니다. 새로 추가하는 항목부터 적용됩니다.",
                  );
                }
              } catch (e) {
                setError((e as Error).message);
              }
            }}
            onSave={async () => {
              setBusy(true);
              try {
                const result = await api("settings", "PUT", settings);
                setSettings(result);
                await refresh();
                setNotice(
                  settings.retention_days === 0
                    ? "자동 삭제를 해제했습니다. 기존 파일도 계속 보관합니다."
                    : "설정을 저장했습니다. 자동 삭제는 새로 추가하는 항목부터 적용됩니다.",
                );
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          />
        ) : null}
        {view === "support" ? <PlatformGuide /> : null}
      </div>
      {adding ? (
        <AddLinks
          busy={busy}
          onClose={() => setAdding(false)}
          onRegister={async (body) => {
            const r = await action("jobs", body);
            if (r) {
              setNotice(
                `${r.added.length}개 등록 · 중복 ${r.duplicates.length}개 제외`,
              );
              library();
            }
            return r;
          }}
        />
      ) : null}
    </div>
  );
}
