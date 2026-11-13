export type MediaJob = {
  id: string;
  url: string;
  platform: string;
  status: string;
  mode: string;
  progress: number;
  error_code: string | null;
  error_message: string | null;
  retryable: number;
  note: string | null;
  created_at: number;
  expires_at: number | null;
  metadata: {
    browser_metadata_version?: number;
    media_type?: string;
    title?: string;
    thumbnail?: string;
    uploader?: string;
    duration?: number;
    max_height?: number;
    width?: number;
    height?: number;
    codecs?: string[];
    available_heights?: number[];
  };
  parent_id?: string;
  entry_index?: number | null;
  job_ids?: string[];
  members?: MediaJob[];
  image_count?: number;
  pending_count?: number;
  completed_count?: number;
  display_caption?: string;
  options?: {
    browser_import?: boolean;
    source?: string;
    output_format?: "mp4" | "original";
    height?: number | null;
  };
  files: { id: string; name: string; size: number }[];
};
export type Settings = {
  download_directory?: string;
  folder: string;
  retention_days: number;
  filename_template: string;
  host_storage_root?: string;
  storage_root?: string;
};
export type Health = {
  cooldowns?: { platform: string; until: number }[];
  desktop?: boolean;
  ok: boolean;
  queue: boolean;
  workers: number;
  yt_dlp: string;
  free_bytes: number;
};
export const labels: Record<string, string> = {
  queued_metadata: "정보 확인 대기",
  extracting: "정보 확인 중",
  ready: "다운로드 가능",
  queued_download: "다운로드 대기",
  downloading: "다운로드 중",
  completed: "저장 완료",
  failed: "실패",
  expired: "기간 만료",
  expiring: "정리 중",
  expanded: "목록 펼침",
  recording: "가져오는 중",
};
export const names: Record<string, string> = {
  instagram: "Instagram",
  youtube: "YouTube",
  vimeo: "Vimeo",
  tiktok: "TikTok",
  x: "X",
  threads: "Threads",
  facebook: "Facebook",
  recording: "녹화·변환",
};
export const busyStates = new Set([
  "queued_metadata",
  "extracting",
  "queued_download",
  "downloading",
  "recording",
  "expiring",
]);
export const sizeLabel = (n: number) =>
  n >= 1024 ** 3
    ? `${(n / 1024 ** 3).toFixed(1)} GB`
    : `${(n / 1024 ** 2).toFixed(1)} MB`;
export function duration(n?: number) {
  return n
    ? `${Math.floor(n / 60)}:${Math.floor(n % 60)
        .toString()
        .padStart(2, "0")}`
    : "—";
}
