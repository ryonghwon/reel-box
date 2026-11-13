"use strict";
const {
  app,
  BrowserWindow,
  Menu,
  session,
  ipcMain,
  dialog,
  shell,
  desktopCapturer,
} = require("electron");
const path = require("node:path"),
  fs = require("node:fs"),
  crypto = require("node:crypto"),
  http = require("node:http");
const { spawn, execFile } = require("node:child_process");
let window,
  backend,
  origin = "",
  quitting = false,
  ready = false,
  log;
// Keep the existing library and Instagram session when the display name changes.
app.setPath(
  "userData",
  process.env.REELBOX_USER_DATA_DIR
    ? path.resolve(process.env.REELBOX_USER_DATA_DIR)
    : path.join(app.getPath("appData"), "reelbox-desktop"),
);
app.setName("Reel Box");
const instance = app.requestSingleInstanceLock();
if (!instance) app.quit();
else {
  app.on("second-instance", () => {
    if (window) {
      if (window.isMinimized()) window.restore();
      window.show();
      window.focus();
    }
  });
  app.whenReady().then(boot).catch(fail);
  app.on("window-all-closed", () => app.quit());
  app.on("before-quit", (event) => {
    if (quitting) return;
    event.preventDefault();
    quitting = true;
    void shutdown().finally(() => app.quit());
  });
}
function request(pathname, token) {
  return new Promise((resolve, reject) => {
    const r = http.get(
      origin + pathname,
      { headers: { "X-API-Key": token }, timeout: 2000 },
      (res) => {
        let body = "";
        res.on("data", (b) => (body += b));
        res.on("end", () => {
          if (res.statusCode !== 200) return reject(Error("Service not ready"));
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(e);
          }
        });
      },
    );
    r.on("error", reject);
    r.on("timeout", () => r.destroy(Error("Timed out")));
  });
}
function post(pathname, token, payload) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(payload);
    const r = http.request(
      origin + pathname,
      {
        method: "POST",
        headers: {
          "X-API-Key": token,
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(body),
        },
        timeout: 10000,
      },
      (res) => {
        let result = "";
        res.on("data", (b) => (result += b));
        res.on("end", () => {
          try {
            const data = JSON.parse(result);
            if (res.statusCode !== 200)
              return reject(
                Error(data.detail || "저장 폴더를 변경할 수 없습니다."),
              );
            resolve(data);
          } catch (e) {
            reject(e);
          }
        });
      },
    );
    r.on("error", reject);
    r.on("timeout", () => r.destroy(Error("응답 시간이 초과되었습니다.")));
    r.end(body);
  });
}
function external(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol === "https:") void shell.openExternal(url);
  } catch {}
}
function trusted(event) {
  return (
    window &&
    !window.isDestroyed() &&
    event.sender === window.webContents &&
    event.senderFrame?.url.startsWith(origin + "/") &&
    origin !== ""
  );
}
async function boot() {
  const base = app.isPackaged ? process.resourcesPath : __dirname;
  const runtime = app.isPackaged
    ? path.join(base, "runtime")
    : path.join(
        base,
        "payload",
        process.platform === "darwin" ? "mac-arm64" : "win-x64",
      );
  const backendDir = app.isPackaged
    ? path.join(base, "backend")
    : path.resolve(base, "../backend");
  const web = path.join(base, "web");
  const user = app.getPath("userData");
  const data = path.join(user, "data");
  const downloads = process.env.REELBOX_DOWNLOAD_DIR
    ? path.resolve(process.env.REELBOX_DOWNLOAD_DIR)
    : path.join(app.getPath("videos"), "Reelbox Library");
  fs.mkdirSync(data, { recursive: true });
  fs.mkdirSync(downloads, { recursive: true });
  fs.mkdirSync(path.join(user, "logs"), { recursive: true });
  const logPath = path.join(user, "logs", "desktop.log");
  if (fs.existsSync(logPath) && fs.statSync(logPath).size > 2 * 1024 ** 2)
    fs.renameSync(logPath, logPath + ".previous");
  log = fs.createWriteStream(logPath, { flags: "a" });
  const token = crypto.randomBytes(32).toString("hex");
  const python = path.join(
    runtime,
    "python",
    process.platform === "win32" ? "python.exe" : "bin/python3",
  );
  const bin = path.join(runtime, "bin");
  for (const f of [
    python,
    path.join(bin, process.platform === "win32" ? "ffmpeg.exe" : "ffmpeg"),
    path.join(bin, process.platform === "win32" ? "ffprobe.exe" : "ffprobe"),
    path.join(bin, process.platform === "win32" ? "node.exe" : "node"),
    path.join(web, "index.html"),
  ])
    if (!fs.existsSync(f))
      throw Error(
        "필수 앱 파일이 없습니다. 앱 전체를 다시 설치하세요: " +
          path.basename(f),
      );
  const partition = session.fromPartition("reelbox");
  window = new BrowserWindow({
    width: 1320,
    height: 880,
    minWidth: 780,
    minHeight: 600,
    title: "Reel Box",
    backgroundColor: "#f5f5f5",
    autoHideMenuBar: true,
    webPreferences: {
      session: partition,
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      webviewTag: false,
    },
  });
  window.webContents.setWindowOpenHandler(({ url }) => {
    external(url);
    return { action: "deny" };
  });
  window.webContents.on("will-navigate", (event, url) => {
    if (origin && new URL(url).origin === origin) return;
    event.preventDefault();
    external(url);
  });
  partition.setPermissionCheckHandler(
    (_contents, permission, requestingOrigin) =>
      requestingOrigin === origin && permission === "display-capture",
  );
  partition.setPermissionRequestHandler((contents, permission, callback) =>
    callback(
      contents === window.webContents &&
        contents.getURL().startsWith(origin + "/") &&
        permission === "display-capture",
    ),
  );
  partition.setDisplayMediaRequestHandler(
    async (request, callback) => {
      if (request.securityOrigin !== origin || !request.userGesture) {
        callback({});
        return;
      }
      try {
        const sources = await desktopCapturer.getSources({
          types: ["window", "screen"],
          thumbnailSize: { width: 0, height: 0 },
        });
        const list = sources
          .filter((s) => !s.name.startsWith("Reel Box"))
          .slice(0, 18);
        const result = await dialog.showMessageBox(window, {
          type: "question",
          title: "녹화할 화면 선택",
          message: "공유할 창이나 화면을 직접 선택하세요.",
          detail: "선택한 화면만 녹화됩니다. 취소하면 녹화하지 않습니다.",
          buttons: ["취소", ...list.map((s) => s.name)],
          defaultId: 0,
          cancelId: 0,
          checkboxLabel:
            process.platform === "win32" ? "시스템 오디오 포함" : undefined,
          checkboxChecked: false,
        });
        const chosen = list[result.response - 1];
        if (!chosen) {
          callback({});
          return;
        }
        callback({
          video: chosen,
          ...(process.platform === "win32" &&
          request.audioRequested &&
          result.checkboxChecked
            ? { audio: "loopback" }
            : {}),
        });
      } catch {
        callback({});
      }
    },
    { useSystemPicker: true },
  );
  partition.on("will-download", (_event, item) => {
    const name = path
      .basename(item.getFilename())
      .replace(/[<>:"/\\|?*\x00-\x1f]/g, "_");
    item.setSaveDialogOptions({
      title: "다른 위치에 저장",
      defaultPath: path.join(app.getPath("downloads"), name),
    });
    item.once("done", (_e, state) => {
      if (state !== "completed" && state !== "cancelled" && !quitting)
        dialog.showErrorBox(
          "파일 저장 실패",
          "저장 위치와 디스크 공간을 확인한 뒤 다시 시도하세요.",
        );
    });
  });
  ipcMain.handle("reelbox:info", (event) => {
    if (!trusted(event)) throw Error("Invalid sender");
    let layout = "grid";
    try {
      const saved = JSON.parse(
        fs.readFileSync(path.join(user, "ui-settings.json"), "utf8"),
      );
      if (["grid", "compact", "list"].includes(saved.layout))
        layout = saved.layout;
    } catch {}
    return {
      platform: process.platform,
      version: app.getVersion(),
      storageRoot: downloads,
      layout,
    };
  });
  ipcMain.handle("reelbox:set-layout", (event, layout) => {
    if (!trusted(event) || !["grid", "compact", "list"].includes(layout))
      throw Error("Invalid view");
    const target = path.join(user, "ui-settings.json");
    fs.writeFileSync(target + ".tmp", JSON.stringify({ layout }));
    fs.renameSync(target + ".tmp", target);
  });
  ipcMain.handle("reelbox:open-library", async (event) => {
    if (!trusted(event)) throw Error("Invalid sender");
    const settings = await request("/api/settings", token);
    const target = settings.download_directory;
    if (!fs.existsSync(target))
      throw Error("저장 폴더를 찾을 수 없습니다. 디스크 연결을 확인하세요.");
    return shell.openPath(target);
  });
  ipcMain.handle("reelbox:choose-library", async (event) => {
    if (!trusted(event)) throw Error("Invalid sender");
    const current = await request("/api/settings", token);
    const chosen = await dialog.showOpenDialog(window, {
      title: "다운로드 폴더 선택",
      defaultPath: current.download_directory,
      properties: ["openDirectory", "createDirectory"],
      buttonLabel: "이 폴더 사용",
    });
    if (chosen.canceled || !chosen.filePaths[0]) return null;
    return post("/api/storage/location", token, { path: chosen.filePaths[0] });
  });
  ipcMain.handle("reelbox:open-logs", async (event) => {
    if (!trusted(event)) throw Error("Invalid sender");
    return shell.openPath(path.join(user, "logs"));
  });
  Menu.setApplicationMenu(
    Menu.buildFromTemplate(
      process.platform === "darwin"
        ? [
            {
              label: "Reel Box",
              submenu: [
                { role: "about" },
                { type: "separator" },
                { role: "quit" },
              ],
            },
            { role: "editMenu" },
            { role: "viewMenu" },
            { role: "windowMenu" },
          ]
        : [
            { label: "파일", submenu: [{ role: "quit" }] },
            { role: "editMenu" },
            { role: "viewMenu" },
          ],
    ),
  );
  await window.loadFile(path.join(__dirname, "splash.html"));
  const env = {
    ...process.env,
    REELBOX_DESKTOP: "1",
    DATA_DIR: data,
    DOWNLOAD_ROOT: downloads,
    API_TOKEN: token,
    PYTHONHOME: path.join(runtime, "python"),
    PYTHONPATH: backendDir,
    PYTHONNOUSERSITE: "1",
    PYTHONDONTWRITEBYTECODE: "1",
    PYTHONUNBUFFERED: "1",
    REELBOX_WEB_DIR: web,
    REELBOX_NODE: path.join(
      bin,
      process.platform === "win32" ? "node.exe" : "node",
    ),
    PATH: bin + path.delimiter + (process.env.PATH || ""),
  };
  backend = spawn(python, ["-m", "app.desktop_server"], {
    cwd: backendDir,
    env,
    windowsHide: true,
    detached: process.platform !== "win32",
    stdio: ["pipe", "pipe", "pipe"],
  });
  backend.stderr.on("data", (chunk) => log.write(chunk));
  backend.on("error", fail);
  backend.on("exit", (code, signal) => {
    ready = false;
    if (!quitting)
      fail(
        Error(
          `다운로드 서비스가 종료되었습니다 (${code ?? signal}). 앱을 다시 실행해 주세요.`,
        ),
      );
  });
  let output = "";
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(
      () =>
        reject(
          Error("앱 준비 시간이 초과되었습니다. 로그 폴더를 확인해 주세요."),
        ),
      60000,
    );
    backend.stdout.on("data", (chunk) => {
      const text = chunk.toString();
      log.write(text);
      output += text;
      for (const line of output.split("\n").slice(0, -1)) {
        if (line.startsWith("REELBOX_READY ")) {
          try {
            const { port } = JSON.parse(line.slice(14));
            if (!Number.isInteger(port) || port < 1 || port > 65535)
              throw Error("Invalid port");
            origin = `http://127.0.0.1:${port}`;
            clearTimeout(timeout);
            resolve();
          } catch (e) {
            clearTimeout(timeout);
            reject(e);
          }
        }
      }
      output = output.slice(output.lastIndexOf("\n") + 1);
    });
    backend.once("error", (e) => {
      clearTimeout(timeout);
      reject(e);
    });
    backend.once("exit", () => {
      clearTimeout(timeout);
      reject(Error("다운로드 서비스를 시작하지 못했습니다."));
    });
  });
  partition.webRequest.onBeforeSendHeaders(
    { urls: [origin + "/*"] },
    (details, callback) =>
      callback({
        requestHeaders: { ...details.requestHeaders, "X-API-Key": token },
      }),
  );
  for (let n = 0; n < 100; n++) {
    try {
      const health = await request("/api/health", token);
      if (health.queue && health.ffmpeg) {
        ready = true;
        break;
      }
    } catch {}
    await new Promise((r) => setTimeout(r, 200));
  }
  if (!ready) throw Error("내장 영상 도구를 준비하지 못했습니다.");
  require("./browser-window.cjs").setup({
    parent: window,
    trusted,
    origin: () => origin,
    token,
    runtime,
    user,
  });
  await window.loadURL(origin + "/");
  log.write(
    JSON.stringify({
      event: "ready",
      version: app.getVersion(),
      platform: process.platform,
      architecture: process.arch,
    }) + "\n",
  );
}
async function shutdown() {
  if (!backend || backend.exitCode !== null) return;
  backend.stdin.end();
  await Promise.race([
    new Promise((resolve) => backend.once("exit", resolve)),
    new Promise((resolve) => setTimeout(resolve, 10000)),
  ]);
  if (backend.exitCode === null) {
    if (process.platform === "win32")
      await new Promise((resolve) =>
        execFile(
          "taskkill",
          ["/PID", String(backend.pid), "/T", "/F"],
          { windowsHide: true },
          resolve,
        ),
      );
    else {
      try {
        process.kill(-backend.pid, "SIGTERM");
      } catch {}
    }
  }
  log?.end();
}
function fail(error) {
  if (quitting) return;
  log?.write(String(error.stack || error) + "\n");
  dialog.showErrorBox(
    "Reel Box를 실행하지 못했습니다",
    error.message || String(error),
  );
  app.quit();
}
