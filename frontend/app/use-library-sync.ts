"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api-client";
import type { MediaJob, Settings, Health } from "./media";

export function useLibrarySync() {
  const [jobs, setJobs] = useState<MediaJob[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [loaded, setLoaded] = useState(false);
  const syncTime = useRef(0);
  const pendingRefresh = useRef<Promise<void> | null>(null);
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
  return { jobs, settings, setSettings, health, loaded, refresh };
}
