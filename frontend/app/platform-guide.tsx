import { Icon } from "./ui";
const platforms = [
  [
    "Instagram",
    "Reels · 영상 · 사진 · 여러 장의 게시물",
    "사진은 게시물별로 묶고 영상은 개별 항목으로 표시합니다. 로그인이 필요한 항목은 앱의 Instagram 창에서 로그인한 뒤 재시도할 수 있습니다.",
  ],
  [
    "Instagram 저장 목록",
    "ZIP · JSON · HTML",
    "계정 센터에서 내보낸 저장 목록을 가져옵니다. 같은 링크는 중복 등록하지 않으며, 중단된 가져오기는 이어서 진행할 수 있습니다.",
  ],
  [
    "YouTube",
    "영상 · Shorts · 재생목록 · 채널 · 오디오",
    "최고 화질 또는 확인된 해상도를 선택합니다. 재생목록·채널은 링크 추가에서 허용하면 한 번에 최대 100개를 가져옵니다.",
  ],
  [
    "Vimeo",
    "개별 영상",
    "공개 영상의 화질을 선택할 수 있습니다. 로그인·비밀번호·소유자 제한이 있는 영상은 다운로드되지 않을 수 있습니다.",
  ],
  [
    "TikTok · X · Facebook · Threads",
    "영상 · 사진 · 여러 첨부물",
    "사이트가 제공하는 미디어를 구분해 저장합니다. 비공개 게시물, 로그인 제한, 삭제된 게시물은 실패 이유를 표시합니다. 플랫폼별 첨부물 제공 방식에 따라 지원 범위가 달라집니다.",
  ],
  [
    "화면 녹화",
    "화면·창 · MP4",
    "직접 선택한 화면을 최대 10분·256MB까지 녹화합니다. 소리 포함 여부는 운영체제와 화면 공유 방식에 따라 다릅니다.",
  ],
];
export default function PlatformGuide() {
  return (
    <main className="utility-view">
      <div className="utility-heading">
        <h1>플랫폼 안내</h1>
        <p>
          미디어 종류와 사이트의 접근 권한에 따라 다운로드 가능 여부가
          달라집니다.
        </p>
      </div>
      <section className="panel support-panel">
        {platforms.map(([name, scope, description]) => (
          <div className="support-row" key={name}>
            <strong>{name}</strong>
            <div>
              <h3>{scope}</h3>
              <p>{description}</p>
            </div>
          </div>
        ))}
        <div className="info-box">
          <Icon name="info" size={18} />
          <p>
            Instagram 로그인은 앱의 전용 창에 유지됩니다. 다른 브라우저의
            로그인과는 별개입니다. 로그인 후 실제로 열 수 있는 게시물만
            저장하며, 접근 제한이나 DRM은 우회하지 않습니다.
          </p>
        </div>
      </section>
    </main>
  );
}
