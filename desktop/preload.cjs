"use strict";
const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld(
  "reelboxDesktop",
  Object.freeze({
    openBrowser: (url, id) =>
      ipcRenderer.invoke("reelbox:open-browser", url, id),
    openBrowserBatch: (ids) =>
      ipcRenderer.invoke("reelbox:open-browser-batch", ids),
    setLayout: (layout) => ipcRenderer.invoke("reelbox:set-layout", layout),
    getInfo: () => ipcRenderer.invoke("reelbox:info"),
    openLibrary: () => ipcRenderer.invoke("reelbox:open-library"),
    chooseLibrary: () => ipcRenderer.invoke("reelbox:choose-library"),
    openLogs: () => ipcRenderer.invoke("reelbox:open-logs"),
  }),
);
