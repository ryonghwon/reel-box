"use strict";
const $ = (id) => document.getElementById(id);
let entries = [],
  saving = false,
  batchRunning = false;
function status(t) {
  $("status").textContent = t;
}
function busy(value) {
  saving = value;
  const blocked = value || batchRunning;
  for (const id of ["inspect", "save", "url", "choices"])
    $(id).disabled = blocked;
  document.querySelector("#go button").disabled = blocked;
  $("save").disabled = blocked || !$("choices").value;
}
$("go").onsubmit = async (event) => {
  event.preventDefault();
  try {
    busy(true);
    await window.viewer.navigate($("url").value);
    entries = [];
    $("choices").replaceChildren(new Option("미디어를 먼저 확인하세요", ""));
    $("preview").removeAttribute("src");
    status("게시물을 연 뒤 영상을 재생하거나 이미지를 화면에 표시하세요.");
  } catch (e) {
    status(e.message);
  } finally {
    busy(false);
  }
};
$("inspect").onclick = async () => {
  try {
    busy(true);
    const r = await window.viewer.inspect();
    entries = r.items;
    $("url").value = r.source;
    $("choices").replaceChildren(
      new Option("저장할 미디어 선택", ""),
      ...entries.map((e) => new Option(e.label, e.id)),
    );
    $("preview").removeAttribute("src");
    status(
      r.message ||
        `${entries.length}개 후보를 확인했습니다. 화면의 미디어와 일치하는 항목을 선택하세요.`,
    );
  } catch (e) {
    entries = [];
    $("choices").replaceChildren(new Option("미디어를 다시 확인하세요", ""));
    status(e.message);
  } finally {
    busy(false);
  }
};
$("choices").onchange = () => {
  const entry = entries.find((e) => e.id === $("choices").value);
  $("save").disabled = saving || !entry;
  if (entry?.preview) $("preview").src = entry.preview;
  else $("preview").removeAttribute("src");
};
$("save").onclick = async () => {
  try {
    busy(true);
    status("선택한 미디어를 저장하고 있습니다… 창을 닫지 마세요.");
    const r = await window.viewer.save($("choices").value);
    status(r.message);
    $("choices").value = "";
  } catch (e) {
    status(e.message);
  } finally {
    busy(false);
  }
};
window.viewer
  .state()
  .then((s) => {
    $("url").value = s.source;
  })
  .catch((e) => status(e.message));
async function sync() {
  try {
    const s = await window.viewer.state(),
      b = s.batch;
    batchRunning = b.running;
    busy(saving);
    $("batch").hidden = !b.posts.length;
    $("batch-status").textContent = b.message;
    $("batch-start").disabled = b.running || saving || b.status === "completed";
    $("batch-start").textContent =
      b.status === "paused" ? "일괄 계속" : "일괄 시작";
    $("batch-pause").disabled = !b.running;
    if (b.running) $("url").value = s.source;
  } catch {
  } finally {
    setTimeout(sync, 1000);
  }
}
$("batch-start").onclick = async () => {
  try {
    await window.viewer.start();
  } catch (e) {
    status(e.message);
  }
};
$("batch-pause").onclick = async () => {
  try {
    await window.viewer.pause();
  } catch (e) {
    status(e.message);
  }
};
void sync();
