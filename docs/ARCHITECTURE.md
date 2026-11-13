# 구조

## 실행 경로

데스크톱은 Electron이 FastAPI 로컬 서버를 실행하고 정적 웹 화면을 표시합니다. 서버는 루프백 인터페이스의 임의 포트를 사용합니다. 앱을 종료하면 서버와 로컬 작업 프로세스도 종료합니다. 저장된 대기 상태는 다음 실행 때 복구합니다.

Docker는 Next.js가 API 요청을 FastAPI로 전달합니다. Redis/RQ worker가 작업을 실행하고 maintenance가 대기 작업과 보관 기간을 관리합니다.

## 모듈

| 경로 | 책임 |
| --- | --- |
| `frontend/app/page.tsx` | 화면 탐색과 사용자 동작 연결 |
| `frontend/app/use-library-sync.ts` | 작업·상태 동기화와 주기적 갱신 |
| `frontend/app/library.ts` | 사진 묶음 구성과 선택 항목 확장 |
| `frontend/app/media.ts` | 미디어 데이터 형식, 상태와 표시 규칙 |
| `frontend/app/api-client.ts` | API 요청과 오류 응답 처리 |
| `backend/app/main.py` | 앱 수명주기와 요청 인증 |
| `backend/app/routes/` | 작업, 설정, 가져오기, 내보내기, 녹화 API |
| `backend/app/schemas.py` | API 입력 검증 |
| `backend/app/job_listing.py` | 작업·파일 스냅샷 조회 |
| `backend/app/tasks.py` | 정보 확인과 파일 저장 작업 |
| `backend/app/extractor.py` | 플랫폼 추출과 미디어 처리 |
| `backend/app/storage.py` | 저장 경로, 파일명, 공간 확인 |
| `backend/app/db.py` | SQLite 상태와 데이터 이관 |
| `desktop/browser-*.cjs` | Instagram 창, 미디어 연결, 로그인 재시도 |

## 작업과 파일

등록한 URL은 정규화한 뒤 플랫폼·다운로드 모드와 함께 중복 확인합니다. 여러 첨부물이 있는 게시물은 원본 작업과 첨부물 작업의 관계로 저장합니다. UI는 사진 첨부물을 하나의 묶음으로 표시하고 영상은 개별 항목으로 표시합니다.

작업에는 등록 시점의 저장 설정을 기록합니다. 전역 저장 폴더를 변경해도 기존 작업의 파일 위치는 유지합니다. 파일 보관 정책을 끄면 기존 삭제 예약도 해제합니다.

동기화 API는 변경된 작업과 현재 작업 ID 목록을 함께 반환합니다. 화면은 변경 항목을 합치고 삭제된 ID를 제거합니다. ZIP 내보내기는 대상 파일을 임시 스냅샷으로 고정한 뒤 순차적으로 읽어, 대량 파일의 동시 열기를 피합니다.

## 인증과 접근

데스크톱 서버는 실행마다 생성한 내부 인증 값을 사용합니다. Docker에서는 `.env`의 `API_TOKEN`을 웹 서버와 API에 함께 적용합니다. 내부 토큰은 사용자의 플랫폼 계정 토큰과 별개입니다.

Instagram 세션은 앱 전용 프로필에 저장합니다. 앱은 공식 화면에서 정상적으로 열린 미디어를 처리하며 외부 브라우저의 계정 정보를 읽지 않습니다. 플랫폼 추출 요청은 허용된 공개 네트워크 주소로 제한합니다.
