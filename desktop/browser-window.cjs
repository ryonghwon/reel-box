"use strict";
const {
  app,
  BrowserWindow,
  WebContentsView,
  session,
  ipcMain,
  dialog,
} = require("electron");
const path = require("node:path"),
  fs = require("node:fs"),
  crypto = require("node:crypto"),
  http = require("node:http");
const { pathToFileURL } = require("node:url"),
  { pipeline } = require("node:stream/promises"),
  { Readable, Transform } = require("node:stream");
const { execFile } = require("node:child_process");
const { postURL, siteURL, mediaURL, choices } = require("./browser-media.cjs");
const {
  inspectScript,
  advanceScript,
  playScript,
} = require("./browser-page.cjs");
const { createBatch } = require("./browser-batch.cjs");
function setup({ parent, trusted, origin, token, runtime, user }) {
  let win,
    view,
    source = "",
    items = new Map(),
    observed = new Set(),
    saving = false,
    generation = 0,
    quitting = false,
    selectedTarget = null,
    lastMetadata = "";
  app.on("before-quit", () => {
    quitting = true;
    batch.pause();
  });
  const toolbar = path.join(__dirname, "browser.html"),
    toolbarURL = pathToFileURL(toolbar).href;
  const browsing = session.fromPartition("persist:reelbox-instagram");
  browsing.setPermissionRequestHandler((_w, _p, callback) => callback(false));
  browsing.setPermissionCheckHandler(() => false);
  // Observe only URLs that this dedicated viewer fetched during normal site playback.
  // No cookies, credentials, authorization headers or page application state are read.
  browsing.webRequest.onCompleted(
    { urls: ["https://*.cdninstagram.com/*", "https://*.fbcdn.net/*"] },
    (details) => {
      if (
        !view ||
        view.webContents.isDestroyed() ||
        details.webContentsId !== view.webContents.id ||
        details.statusCode >= 400
      )
        return;
      if (!/\.mp4(?:\?|$)/i.test(details.url)) return;
      observed.add(details.url);
      if (observed.size > 300) observed.delete(observed.values().next().value);
    },
  );
  function guard(event) {
    if (
      !win ||
      win.isDestroyed() ||
      event.sender !== win.webContents ||
      event.senderFrame?.url !== toolbarURL
    )
      throw Error("Invalid sender");
  }
  function reset() {
    items.clear();
    observed.clear();
    generation++;
  }
  function layout() {
    if (win && !win.isDestroyed() && view) {
      const [width, height] = win.getContentSize();
      view.setBounds({
        x: 0,
        y: 240,
        width,
        height: Math.max(0, height - 240),
      });
    }
  }
  function create() {
    win = new BrowserWindow({
      parent,
      width: 1100,
      height: 880,
      minWidth: 840,
      minHeight: 640,
      title: "Reel Box · Instagram에서 저장",
      backgroundColor: "#fff",
      webPreferences: {
        preload: path.join(__dirname, "browser-preload.cjs"),
        nodeIntegration: false,
        contextIsolation: true,
        sandbox: true,
      },
    });
    view = new WebContentsView({
      webPreferences: {
        session: browsing,
        nodeIntegration: false,
        contextIsolation: true,
        sandbox: true,
        webSecurity: true,
      },
    });
    win.contentView.addChildView(view);
    layout();
    win.on("resize", layout);
    win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
    win.webContents.on("will-navigate", (e) => e.preventDefault());
    view.webContents.setWindowOpenHandler(({ url }) => {
      if (siteURL(url)) void view.webContents.loadURL(url).catch(() => {});
      return { action: "deny" };
    });
    view.webContents.on("will-navigate", (e, url) => {
      if (!siteURL(url)) e.preventDefault();
    });
    view.webContents.on("will-redirect", (e, url) => {
      if (!siteURL(url)) e.preventDefault();
    });
    view.webContents.on(
      "did-start-navigation",
      (_e, _url, _inPlace, isMainFrame) => {
        if (isMainFrame) reset();
      },
    );
    view.webContents.on("did-navigate-in-page", (_e, _url, isMainFrame) => {
      if (isMainFrame) reset();
    });
    win.on("close", (e) => {
      if ((saving || batch.get().running) && !quitting) {
        e.preventDefault();
        void dialog.showMessageBox(win, {
          message:
            "저장 또는 일괄 처리 중입니다. 일시정지한 뒤 창을 닫아 주세요.",
          buttons: ["확인"],
        });
      }
    });
    win.on("closed", () => {
      if (view && !view.webContents.isDestroyed()) view.webContents.close();
      view = null;
      win = null;
      reset();
    });
    void win.loadFile(toolbar);
  }
  const queuePath = path.join(user, "browser-queue.json");
  let previous;
  try {
    previous = JSON.parse(fs.readFileSync(queuePath, "utf8"));
    if (!Array.isArray(previous.posts) || previous.posts.length > 500)
      previous = undefined;
  } catch {}
  const batch = createBatch(
    {
      persist: (state) => {
        fs.writeFileSync(queuePath + ".tmp", JSON.stringify(state));
        fs.renameSync(queuePath + ".tmp", queuePath);
      },
      delay: (ms) => new Promise((r) => setTimeout(r, ms)),
      load: loadPost,
      inspect: async () => {
        await view.webContents.executeJavaScript(playScript, true);
        return inspectPage();
      },
      advance: async () => {
        observed.clear();
        items.clear();
        generation++;
        return view.webContents.executeJavaScript(advanceScript, true);
      },
      save: async (choice, context) =>
        saveChoice({
          ...choice,
          targetId: context.targetId,
          postIndex: context.index,
          deferMerge: context.deferMerge,
        }),
      complete: async (targetId, savedIds) =>
        api("/api/imports/browser-complete-post", {
          target_id: targetId,
          saved_ids: savedIds,
        }),
      outcome: async (ids, message, code) =>
        api("/api/imports/browser-outcome", { ids, message, code }),
    },
    previous,
  );
  async function loadPost(url) {
    source = postURL(url);
    reset();
    if (!win || win.isDestroyed()) create();
    await view.webContents.loadURL(source);
  }
  async function inspectPage() {
    const snapshot = generation;
    const data = await view.webContents.executeJavaScript(inspectScript);
    if (data.login) return { ...data, source, items: [] };
    const current = postURL(view.webContents.getURL());
    if (snapshot !== generation)
      throw Error("게시물이 바뀌었습니다. 다시 확인하세요.");
    if (data.media.some((m) => m.encrypted)) throw Error("ACCESS_RESTRICTED");
    const found = choices(data.media, [...observed]).map((choice) => ({
      ...choice,
      source: current,
      title: data.title,
      uploader: data.uploader,
      silent: data.silent,
      generation,
    }));
    const metadataKey = JSON.stringify([current, data.title, data.uploader]);
    if (
      data.media.length &&
      data.uploader &&
      !data.restricted &&
      metadataKey !== lastMetadata
    ) {
      await api("/api/imports/browser-metadata", {
        source: current,
        title: data.title,
        uploader: data.uploader,
      });
      lastMetadata = metadataKey;
    }
    return { ...data, source: current, items: found };
  }
  ipcMain.handle("reelbox:open-browser", async (event, url, targetId) => {
    if (!trusted(event)) throw Error("Invalid sender");
    if (saving || batch.get().running)
      throw Error("열려 있는 창의 작업을 먼저 일시정지하세요.");
    selectedTarget = null;
    if (targetId) {
      const prepared = await api("/api/imports/browser-targets", {
        ids: [targetId],
      });
      selectedTarget = prepared.posts?.[0]?.targets?.[0] || null;
      if (selectedTarget?.index !== null && selectedTarget?.index !== undefined)
        batch.set(prepared.posts);
    }
    await loadPost(url);
    await win.loadFile(toolbar);
    win.show();
    win.focus();
    return true;
  });
  ipcMain.handle("reelbox:open-browser-batch", async (event, ids) => {
    if (!trusted(event) || !Array.isArray(ids) || ids.length > 500)
      throw Error("Invalid sender or selection");
    if (saving || batch.get().running)
      throw Error("기존 일괄 처리를 먼저 일시정지하세요.");
    const prepared = await api("/api/imports/browser-targets", { ids });
    if (!prepared.posts.length)
      throw Error("로그인으로 재확인할 Instagram 항목이 없습니다.");
    batch.set(prepared.posts);
    selectedTarget = null;
    await loadPost(prepared.posts[0].url);
    await win.loadFile(toolbar);
    win.show();
    win.focus();
    return true;
  });
  ipcMain.handle("reelbox:browser-state", (event) => {
    guard(event);
    return { source, batch: batch.get(), saving };
  });
  ipcMain.handle("reelbox:browser-batch-start", (event) => {
    guard(event);
    if (saving) throw Error("파일을 저장 중입니다.");
    void batch.run().catch(() => {});
    return true;
  });
  ipcMain.handle("reelbox:browser-batch-pause", (event) => {
    guard(event);
    batch.pause();
    return true;
  });
  ipcMain.handle("reelbox:browser-go", async (event, url) => {
    guard(event);
    if (saving || batch.get().running)
      throw Error("일괄 처리를 먼저 일시정지하세요.");
    selectedTarget = null;
    await loadPost(url);
    return true;
  });
  ipcMain.handle("reelbox:browser-inspect", async (event) => {
    guard(event);
    if (saving || batch.get().running)
      throw Error("일괄 처리를 먼저 일시정지하세요.");
    items.clear();
    const data = await inspectPage();
    source = data.source;
    if (selectedTarget && (selectedTarget.index !== null || data.hasNext)) {
      batch.set([{ url: source, targets: [selectedTarget] }]);
      throw Error(
        "여러 미디어가 있는 게시물입니다. 일괄 시작을 눌러 순서를 확인하고 기존 항목에 연결하세요.",
      );
    }
    for (const choice of data.items) {
      const id = crypto.randomBytes(12).toString("hex");
      items.set(id, {
        ...choice,
        targetId: selectedTarget?.index == null ? selectedTarget?.id || "" : "",
        postIndex: 0,
        deferMerge: data.hasNext,
      });
    }
    return {
      source,
      items: [...items].map(([id, c]) => ({
        id,
        label: c.label,
        preview: validPreview(c.preview),
      })),
      message: data.items.length
        ? ""
        : "정상 재생 미디어를 확인하지 못했습니다. 로그인 후 게시물을 열고 다시 확인하세요.",
    };
  });
  ipcMain.handle("reelbox:browser-save", async (event, id) => {
    guard(event);
    if (batch.get().running) throw Error("일괄 처리 중입니다.");
    return saveChoice(items.get(id));
  });
  async function saveChoice(choice) {
    if (saving) throw Error("이미 저장 중입니다.");
    if (
      !choice ||
      choice.generation !== generation ||
      choice.source !== postURL(view.webContents.getURL())
    )
      throw Error(
        "게시물이 바뀌었거나 확인이 만료되었습니다. 미디어를 다시 확인하세요.",
      );
    saving = true;
    const temp = fs.mkdtempSync(path.join(user, "browser-save-"));
    try {
      let output, mime;
      if (choice.kind === "image") {
        output = path.join(temp, "image");
        await download(choice.image, output, 64 * 1024 ** 2);
        mime = "application/octet-stream";
      } else {
        const video = path.join(temp, "video.mp4"),
          audio = path.join(temp, "audio.mp4");
        await download(choice.video, video);
        if (choice.audio) await download(choice.audio, audio);
        output = path.join(temp, "saved.mp4");
        const inputs = [
          "-protocol_whitelist",
          "file,pipe",
          "-i",
          video,
          ...(choice.audio
            ? ["-protocol_whitelist", "file,pipe", "-i", audio]
            : []),
        ];
        await run(
          path.join(
            runtime,
            "bin",
            process.platform === "win32" ? "ffmpeg.exe" : "ffmpeg",
          ),
          [
            "-v",
            "error",
            "-nostdin",
            "-y",
            ...inputs,
            "-map",
            "0:v:0",
            "-map",
            choice.audio ? "1:a:0" : "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            output,
          ],
        );
        mime = "video/mp4";
      }
      const result = await upload(output, mime, choice);
      return {
        ...result,
        message: result.merged
          ? "기존 실패 항목에 연결했습니다. 보관함에 완료 항목 하나로 표시됩니다."
          : result.duplicate
            ? "이미 저장된 파일입니다. 제목·작성자 정보를 갱신했습니다."
            : "보관함에 저장했습니다.",
      };
    } catch (error) {
      throw Error(cleanError(error));
    } finally {
      saving = false;
      fs.rmSync(temp, { recursive: true, force: true });
    }
  }
  function api(endpoint, body) {
    return new Promise((resolve, reject) => {
      const encoded = Buffer.from(JSON.stringify(body));
      const req = http.request(
        origin() + endpoint,
        {
          method: "POST",
          headers: {
            "X-API-Key": token,
            "Content-Type": "application/json",
            "Content-Length": encoded.length,
          },
          timeout: 15000,
        },
        (res) => {
          let text = "";
          res.on("data", (c) => {
            if (text.length < 1024 * 1024) text += c;
          });
          res.on("end", () => {
            try {
              const data = JSON.parse(text);
              if (res.statusCode !== 200)
                return reject(
                  Error(
                    typeof data.detail === "string"
                      ? data.detail
                      : "요청을 처리하지 못했습니다.",
                  ),
                );
              resolve(data);
            } catch (e) {
              reject(e);
            }
          });
        },
      );
      req.on("error", reject);
      req.on("timeout", () =>
        req.destroy(Error("응답 시간이 초과되었습니다.")),
      );
      req.end(encoded);
    });
  }
  async function download(raw, target, limit = 2 * 1024 ** 3) {
    const controller = new AbortController(),
      timer = setTimeout(() => controller.abort(), 180000);
    let count = 0,
      lastDiskCheck = 0;
    try {
      const response = await browsing.fetch(mediaURL(raw), {
        credentials: "omit",
        redirect: "error",
        signal: controller.signal,
        headers: { Referer: "https://www.instagram.com/" },
      });
      if (!response.ok || !response.body)
        throw Error(
          "원본 파일을 받지 못했습니다. 게시물을 새로 열고 다시 확인하세요.",
        );
      if (Number(response.headers.get("content-length")) > limit)
        throw Error("파일 크기 한도를 초과했습니다 (이미지 64MB / 영상 2GB).");
      const bound = new Transform({
        transform(chunk, _encoding, done) {
          count += chunk.length;
          if (count > limit)
            return done(
              Error("파일 크기 한도를 초과했습니다 (이미지 64MB / 영상 2GB)."),
            );
          if (Date.now() - lastDiskCheck > 1000) {
            lastDiskCheck = Date.now();
            const disk = fs.statfsSync(user);
            if (disk.bavail * disk.bsize < 256 * 1024 ** 2)
              return done(Error("저장 공간이 부족합니다."));
          }
          done(null, chunk);
        },
      });
      await pipeline(
        Readable.fromWeb(response.body),
        bound,
        fs.createWriteStream(target),
      );
    } finally {
      clearTimeout(timer);
      controller.abort();
    }
  }
  function upload(file, mime, choice) {
    return new Promise((resolve, reject) => {
      const query = new URLSearchParams({
        source: choice.source,
        title: choice.title,
        kind: choice.kind,
        uploader: choice.uploader || "",
        target_id: choice.targetId || "",
        post_index: String(choice.postIndex || 0),
        asset_id: choice.asset || "",
        silent: String(!!choice.silent),
        defer_merge: String(!!choice.deferMerge),
      });
      const r = http.request(
        origin() + "/api/imports/browser-media?" + query,
        {
          method: "POST",
          headers: {
            "X-API-Key": token,
            "Content-Type": mime,
            "Content-Length": fs.statSync(file).size,
          },
          timeout: 120000,
        },
        (res) => {
          let text = "";
          res.on("data", (b) => {
            if (text.length < 16000) text += b;
          });
          res.on("error", reject);
          res.on("end", () => {
            try {
              const d = JSON.parse(text);
              if (res.statusCode !== 200)
                return reject(
                  Error(
                    typeof d.detail === "string"
                      ? d.detail
                      : "보관함에 저장하지 못했습니다.",
                  ),
                );
              resolve(d);
            } catch {
              return reject(Error("보관함 응답을 읽지 못했습니다."));
            }
          });
        },
      );
      r.on("error", reject);
      r.on("timeout", () =>
        r.destroy(Error("보관함 저장 시간이 초과되었습니다.")),
      );
      const input = fs.createReadStream(file);
      input.on("error", (e) => r.destroy(e));
      r.on("close", () => input.destroy());
      input.pipe(r);
    });
  }
}
function run(command, args) {
  return new Promise((resolve, reject) =>
    execFile(
      command,
      args,
      { windowsHide: true, timeout: 600000, maxBuffer: 65536 },
      (error) =>
        error
          ? reject(
              Error(
                "MP4 변환에 실패했습니다. 앱 로그와 저장 공간을 확인하세요.",
              ),
            )
          : resolve(),
    ),
  );
}
function validPreview(raw) {
  try {
    return mediaURL(raw);
  } catch {
    return "";
  }
}
function cleanError(error) {
  const m = String(error.message || error);
  return /https?:\/\//i.test(m)
    ? "미디어 저장에 실패했습니다. 게시물을 새로 열고 다시 확인하세요."
    : m.slice(0, 400);
}
module.exports = { setup };
