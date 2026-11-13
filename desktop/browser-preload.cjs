"use strict";
const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld(
  "viewer",
  Object.freeze({
    navigate: (url) => ipcRenderer.invoke("reelbox:browser-go", url),
    inspect: () => ipcRenderer.invoke("reelbox:browser-inspect"),
    save: (id) => ipcRenderer.invoke("reelbox:browser-save", id),
    state: () => ipcRenderer.invoke("reelbox:browser-state"),
    start: () => ipcRenderer.invoke("reelbox:browser-batch-start"),
    pause: () => ipcRenderer.invoke("reelbox:browser-batch-pause"),
  }),
);
