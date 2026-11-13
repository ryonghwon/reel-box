"use client";
import { useEffect, useRef, useState } from "react";

export default function Recorder({ onSaved }: { onSaved: () => void }) {
  const [capturing, setCapturing] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState("화면 녹화");
  const [source, setSource] = useState("");
  const video = useRef<HTMLVideoElement>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const parts = useRef<Blob[]>([]);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const objectUrl = useRef("");
  const count = useRef(0);
  const mounted = useRef(true);
  const requestId = useRef(0);
  function stop() {
    if (recorder.current?.state === "recording") recorder.current.stop();
    stream.current?.getTracks().forEach((t) => t.stop());
    if (timer.current) clearInterval(timer.current);
    setCapturing(false);
  }
  function setCapture(value: Blob) {
    setBlob(value);
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = URL.createObjectURL(value);
    setUrl(objectUrl.current);
    if (video.current) video.current.srcObject = null;
  }
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (timer.current) clearInterval(timer.current);
      stream.current?.getTracks().forEach((t) => t.stop());
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    };
  }, []);
  useEffect(() => {
    const unload = (e: BeforeUnloadEvent) => {
      if (capturing || blob) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", unload);
    return () => window.removeEventListener("beforeunload", unload);
  }, [capturing, blob]);
  async function start() {
    setError("");
    setHint("");
    if (!navigator.mediaDevices?.getDisplayMedia) {
      setError(
        "이 브라우저는 화면 녹화를 지원하지 않습니다. 데스크톱 Chrome 또는 Edge의 localhost에서 열어 주세요.",
      );
      return;
    }
    setChoosing(true);
    const ticket = ++requestId.current;
    const chooseTimer = setTimeout(() => {
      if (requestId.current === ticket) {
        requestId.current++;
        setChoosing(false);
        setError(
          "화면 선택 창이 열리지 않으면 데스크톱 Chrome 또는 Edge에서 http://localhost:3000을 열어 주세요.",
        );
      }
    }, 30000);
    try {
      const captured = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: { ideal: 30, max: 30 } },
        audio: true,
      });
      clearTimeout(chooseTimer);
      if (requestId.current !== ticket || !mounted.current) {
        captured.getTracks().forEach((t) => t.stop());
        return;
      }
      stream.current = captured;
      const mime = [
        "video/mp4;codecs=avc1.424028,mp4a.40.2",
        "video/webm;codecs=vp8,opus",
        "video/webm",
      ].find((v) => MediaRecorder.isTypeSupported(v));
      if (!mime)
        throw new Error(
          "지원되는 녹화 형식이 없습니다. Chrome 또는 Edge에서 시도하세요.",
        );
      const mr = new MediaRecorder(captured, {
        mimeType: mime,
        videoBitsPerSecond: 2500000,
        audioBitsPerSecond: 128000,
      });
      recorder.current = mr;
      parts.current = [];
      count.current = 0;
      setSeconds(0);
      setBlob(null);
      setUrl("");
      if (video.current) {
        video.current.srcObject = captured;
        void video.current.play().catch(() => {});
      }
      mr.ondataavailable = (e) => {
        if (e.data.size) {
          parts.current.push(e.data);
          count.current += e.data.size;
          if (count.current >= 256 * 1024 ** 2) {
            setHint("녹화가 256MB에 도달해 자동 중지했습니다.");
            stop();
          }
        }
      };
      mr.onstop = () => {
        if (mounted.current) {
          setCapture(new Blob(parts.current, { type: mime }));
          setCapturing(false);
        }
        captured.getTracks().forEach((t) => t.stop());
        if (timer.current) clearInterval(timer.current);
      };
      mr.onerror = () => {
        setError(
          "브라우저에서 녹화 오류가 발생했습니다. 지금까지 수집된 화면을 확인하세요.",
        );
        stop();
      };
      captured.getVideoTracks()[0].onended = stop;
      if (!captured.getAudioTracks().length)
        setHint(
          "오디오가 공유되지 않았습니다. 소리도 필요하면 화면 공유 창의 오디오 옵션을 확인하세요. 운영체제에 따라 오디오 공유가 지원되지 않을 수 있습니다.",
        );
      mr.start(1000);
      setCapturing(true);
      const started = Date.now();
      timer.current = setInterval(() => {
        const elapsed = Math.floor((Date.now() - started) / 1000);
        setSeconds(elapsed);
        if (elapsed >= 600) {
          setHint("10분에 도달해 녹화를 자동 중지했습니다.");
          stop();
        }
      }, 500);
    } catch (e) {
      stream.current?.getTracks().forEach((t) => t.stop());
      const err = e as Error;
      setError(
        err.name === "NotAllowedError"
          ? "화면 공유가 취소되었거나 허용되지 않았습니다. 원할 때 다시 시작하세요."
          : err.message,
      );
    } finally {
      clearTimeout(chooseTimer);
      if (requestId.current === ticket) setChoosing(false);
    }
  }
  async function upload() {
    if (!blob) return;
    setSaving(true);
    setError("");
    try {
      const params = new URLSearchParams({ title, source });
      const res = await fetch(`/api/recordings?${params}`, {
        method: "POST",
        headers: {
          "Content-Type": blob.type.startsWith("video/mp4")
            ? "video/mp4"
            : "video/webm",
        },
        body: blob,
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "저장에 실패했습니다.");
      onSaved();
      setHint(
        "라이브러리에 추가했습니다. MP4 변환 후 미리보기를 확인할 수 있습니다.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="recorder-grid">
      <section className="panel recorder-panel">
        <div className="section-top">
          <div className="section-title">
            <span className={`rec-dot ${capturing ? "on" : ""}`} />
            <h2>{capturing ? "녹화 중" : "화면 녹화"}</h2>
          </div>
          <span className="timer">
            {Math.floor(seconds / 60)
              .toString()
              .padStart(2, "0")}
            :{(seconds % 60).toString().padStart(2, "0")}
          </span>
        </div>
        <div className={`video-stage ${capturing || url ? "has-video" : ""}`}>
          <video
            ref={video}
            src={url || undefined}
            controls={!!url}
            muted={capturing}
            playsInline
          />
          {!capturing && !url ? (
            <div className="recorder-placeholder">
              <span>▣</span>
              <h3>필요한 장면만, 간편하게.</h3>
              <p>
                영상이 재생되는 탭이나 창을 선택하세요.
                <br />
                녹화 후 미리보기가 표시됩니다.
              </p>
            </div>
          ) : null}
          {capturing ? <span className="live-badge">● REC</span> : null}
        </div>
        <div className="record-controls">
          {capturing ? (
            <button className="button stop-button" onClick={stop}>
              ■ 녹화 중지
            </button>
          ) : (
            <button
              className="button primary"
              disabled={choosing || saving}
              onClick={start}
            >
              ●{" "}
              {choosing
                ? "화면 선택 중…"
                : url
                  ? "다시 녹화하기"
                  : "화면 선택 · 녹화 시작"}
            </button>
          )}
          {choosing ? (
            <button
              className="text-button"
              onClick={() => {
                requestId.current++;
                setChoosing(false);
                setHint(
                  "선택을 취소했습니다. 브라우저의 공유 창이 남아 있으면 닫아 주세요.",
                );
              }}
            >
              선택 취소
            </button>
          ) : null}
          <span>최대 10분 · 256MB</span>
        </div>
        {error ? (
          <div className="alert error" role="alert">
            {error}
          </div>
        ) : null}
        {hint ? (
          <div className="alert notice" role="status">
            {hint}
          </div>
        ) : null}
        <div className="record-fields">
          <label>
            제목
            <input
              value={title}
              maxLength={200}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label>
            출처 링크 <small>선택</small>
            <input
              type="url"
              value={source}
              placeholder="https://www.instagram.com/p/…"
              onChange={(e) => setSource(e.target.value)}
            />
          </label>
        </div>
        {blob ? (
          <div className="record-export">
            <span>
              {(blob.size / 1024 ** 2).toFixed(1)} MB ·{" "}
              {blob.type.startsWith("video/mp4") ? "MP4" : "WebM"}
            </span>
            <a
              className="button"
              href={url}
              download={`reelbox-recording.${blob.type.startsWith("video/mp4") ? "mp4" : "webm"}`}
            >
              원본 녹화 저장
            </a>
            <button className="button dark" disabled={saving} onClick={upload}>
              {saving ? "업로드 중…" : "MP4로 저장"}
            </button>
          </div>
        ) : null}
        <div className="existing-record">
          <span>이미 녹화한 파일이 있나요?</span>
          <label className="text-button">
            파일 가져오기
            <input
              type="file"
              accept="video/webm,video/mp4"
              disabled={capturing || saving}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) {
                  if (f.size > 512 * 1024 ** 2) {
                    setError("512MB 이하의 녹화 파일을 선택하세요.");
                    return;
                  }
                  setCapture(f);
                  setError("");
                }
              }}
            />
          </label>
        </div>
      </section>
      <aside className="record-guide">
        <span className="eyebrow">QUICK GUIDE</span>
        <h2>이렇게 녹화하세요</h2>
        <ol>
          <li>
            <strong>원래 사이트에서 영상 열기</strong>
            <p>Instagram 등에서 직접 로그인하고 재생할 영상을 열어 두세요.</p>
          </li>
          <li>
            <strong>영상 탭 선택하기</strong>
            <p>
              ‘화면 선택’을 누르고 해당 탭을 골라요. 소리가 필요하면 탭 오디오도
              공유하세요.
            </p>
          </li>
          <li>
            <strong>재생하고, 녹화 중지</strong>
            <p>원하는 구간을 재생한 뒤 이 앱으로 돌아와 중지하세요.</p>
          </li>
          <li>
            <strong>MP4 파일로 가져가기</strong>
            <p>
              저장하면 720p·30fps MP4로 변환됩니다. 받은 파일은 원하는 AI 도구에
              직접 올리세요.
            </p>
          </li>
        </ol>
        <div className="record-tip">
          <strong>로그인은 사이트에서 직접</strong>
          <p>
            비밀번호와 쿠키는 수집하지 않습니다. 화면 공유는 사용자가 선택한
            대상에만 적용되며, 공유 종료 버튼으로 언제든 중지할 수 있습니다.
          </p>
          <p>
            녹화 권한 창에서 오디오 지원을 확인하세요. DRM 보호 화면은 검게 보일
            수 있으며 이 앱에서 우회하지 않습니다.
          </p>
        </div>
      </aside>
    </div>
  );
}
