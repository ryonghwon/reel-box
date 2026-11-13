// Original Reel Box mark: a film reel resting inside an archive tray.
export default function BrandMark({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        fillRule="evenodd"
        d="M12 2a7 7 0 0 0-6.7 9H3v8a3 3 0 0 0 3 3h12a3 3 0 0 0 3-3v-8h-2.3A7 7 0 0 0 12 2Zm0 2a1.6 1.6 0 1 1 0 3.2A1.6 1.6 0 0 1 12 4ZM8.5 8.5a1.6 1.6 0 1 1 0 3.2 1.6 1.6 0 0 1 0-3.2Zm7 0a1.6 1.6 0 1 1 0 3.2 1.6 1.6 0 0 1 0-3.2ZM12 8a1 1 0 1 1 0 2 1 1 0 0 1 0-2ZM5 13v6a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-6h-4v2H9v-2H5Z"
      />
    </svg>
  );
}
