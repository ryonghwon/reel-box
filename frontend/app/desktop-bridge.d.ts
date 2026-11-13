export {};
declare global {
  interface Window {
    reelboxDesktop?: {
      openBrowser: (url: string, id?: string) => Promise<boolean>;
      openBrowserBatch: (ids: string[]) => Promise<boolean>;
      setLayout: (layout: string) => Promise<void>;
      getInfo: () => Promise<{
        platform: string;
        version: string;
        storageRoot: string;
        layout?: string;
      }>;
      openLibrary: () => Promise<string>;
      chooseLibrary: () => Promise<import("./ui").Settings | null>;
      openLogs: () => Promise<string>;
    };
  }
}
