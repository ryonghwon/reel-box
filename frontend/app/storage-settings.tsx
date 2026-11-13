"use client";
import { Settings } from "./media";
import { Icon } from "./ui";
type Props = {
  settings: Settings;
  storagePath: string;
  desktop: boolean;
  busy: boolean;
  onChange: (value: Settings) => void;
  onOpen: () => void;
  onChoose: () => Promise<void>;
  onSave: () => Promise<void>;
};
export default function StorageSettings({
  settings,
  storagePath,
  desktop,
  busy,
  onChange,
  onOpen,
  onChoose,
  onSave,
}: Props) {
  return (
    <main className="utility-view">
      <div className="utility-heading">
        <h1>저장 설정</h1>
        <p>파일을 저장할 위치와 보관 방식을 설정합니다.</p>
      </div>
      <form
        className="panel settings-panel"
        onSubmit={(e) => {
          e.preventDefault();
          void onSave();
        }}
      >
        <section className="settings-section">
          <h2>다운로드 폴더</h2>
          <p className="field-help">
            선택한 폴더에 원본 파일을 저장하고, 앱에서 목록과 미리보기를
            관리합니다.
          </p>
          <div className="native-storage">
            <p title={storagePath}>{storagePath}</p>
            <div className="settings-actions">
              <button type="button" className="button" onClick={onOpen}>
                <Icon name="folder" size={16} />
                {desktop ? "폴더 열기" : "경로 복사"}
              </button>
              {desktop ? (
                <button
                  type="button"
                  className="button"
                  disabled={busy}
                  onClick={() => void onChoose()}
                >
                  폴더 변경
                </button>
              ) : null}
            </div>
          </div>
          <p className="field-help">
            변경한 위치는 새로 추가하는 항목부터 적용됩니다. 기존 파일은 현재
            위치에 유지됩니다.
          </p>
        </section>
        <section className="settings-section">
          <label className="settings-label">
            자동 삭제
            <select
              aria-label="자동 삭제"
              value={settings.retention_days}
              onChange={(e) =>
                onChange({
                  ...settings,
                  retention_days: Number(e.target.value),
                })
              }
            >
              <option value={0}>자동 삭제 안 함</option>
              {[1, 3, 7, 14, 30, 90, 365].map((n) => (
                <option key={n} value={n}>
                  {n}일 후 삭제
                </option>
              ))}
            </select>
          </label>
          <p className="field-help">
            {settings.retention_days === 0
              ? "직접 삭제할 때까지 파일을 보관합니다. 설정을 저장하면 기존 파일의 삭제 예약도 해제됩니다."
              : "새 항목은 다운로드 완료 후 선택한 기간이 지나면 파일이 삭제됩니다. 기록은 남습니다."}
          </p>
        </section>
        <details className="advanced-settings">
          <summary>고급 설정</summary>
          {!desktop ? (
            <label className="settings-label">
              하위 폴더 이름
              <input
                value={settings.folder}
                onChange={(e) =>
                  onChange({ ...settings, folder: e.target.value })
                }
                required
                maxLength={60}
              />
            </label>
          ) : null}
          <label className="settings-label">
            파일명 규칙
            <input
              value={settings.filename_template}
              onChange={(e) =>
                onChange({ ...settings, filename_template: e.target.value })
              }
            />
          </label>
          <p className="field-help">
            {
              "{date} 날짜 · {platform} 플랫폼 · {title} 제목 · {id} 게시물 ID · {uploader} 작성자"
            }
          </p>
          <p className="field-help">
            파일 충돌을 방지하기 위해 항목별 폴더와 고유 ID를 사용합니다. 저장한
            파일을 직접 이동하면 앱에서 찾을 수 없으므로, 공유할 때는 ‘다른
            위치에 저장’을 이용하세요.
          </p>
        </details>
        <div className="settings-footer">
          <button className="button primary" disabled={busy}>
            설정 저장
            <Icon name="check" size={16} />
          </button>
        </div>
      </form>
    </main>
  );
}
