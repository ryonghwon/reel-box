"use strict";
// One visible browser page at a time. Pausing never discards the current file.
function createBatch(io, initial) {
  let state = initial || {
      posts: [],
      cursor: 0,
      results: [],
      status: "idle",
      message: "",
    },
    running = false,
    stop = false;
  if (state.status === "running") state.status = "paused";
  const emit = () => io.persist({ ...state });
  async function waitMedia(previous = "", metadataOnly = false) {
    for (let attempt = 0; attempt < 15; attempt++) {
      if (stop) throw Error("PAUSED");
      const data = await io.inspect();
      if (data.login) throw Error("LOGIN_REQUIRED");
      if (data.restricted) throw Error("ACCESS_RESTRICTED");
      if (
        metadataOnly
          ? data.uploader && data.media?.length
          : data.items.length === 1 &&
            data.signature !== previous &&
            (!data.items[0].muted || data.silent)
      )
        return data;
      await io.delay(1000);
    }
    throw Error("MEDIA_UNAVAILABLE");
  }
  async function run() {
    if (running) return;
    running = true;
    stop = false;
    state.status = "running";
    emit();
    try {
      while (state.cursor < state.posts.length && !stop) {
        const post = state.posts[state.cursor];
        const saved = [];
        const done = new Set();
        let complete = false;
        state.message = `${state.cursor + 1} / ${state.posts.length} 게시물 확인 중`;
        emit();
        try {
          await io.load(post.url);
          let previous = "";
          if (post.targets.every((t) => t.status === "completed")) {
            await waitMedia("", true);
            state.results.push({
              url: post.url,
              status: "saved",
              count: 0,
              metadataOnly: true,
            });
            state.cursor++;
            emit();
            await io.delay(1800);
            continue;
          }
          for (let index = 0; index < 20; index++) {
            const data = await waitMedia(previous);
            previous = data.signature;
            const root = post.targets.find((t) => t.index === null);
            const target = post.targets.find((t) => t.index === index);
            if (root || target) {
              const choice = data.items[0];
              if (choice.encrypted) throw Error("ACCESS_RESTRICTED");
              const r = await io.save(choice, {
                targetId: target?.id || "",
                index,
                deferMerge: !!root,
              });
              saved.push(r.id);
              if (target) done.add(target.id);
            }
            if (stop) throw Error("PAUSED");
            if (!data.hasNext) {
              complete = true;
              break;
            }
            // Child-only retries stop when every requested slot has been handled.
            if (!root && done.size === post.targets.length) {
              complete = true;
              break;
            }
            if (!(await io.advance())) throw Error("CAROUSEL_REVIEW");
          }
          const root = post.targets.find((t) => t.index === null);
          if (!complete || (!root && done.size !== post.targets.length))
            throw Error("CAROUSEL_REVIEW");
          if (root?.status !== "completed" && root && saved.length)
            await io.complete(root.id, saved);
          state.results.push({
            url: post.url,
            status: "saved",
            count: saved.length,
          });
        } catch (error) {
          const code = error.message;
          if (code === "PAUSED" || code === "LOGIN_REQUIRED") {
            state.status = "paused";
            state.message =
              code === "LOGIN_REQUIRED"
                ? "공식 사이트에 로그인한 뒤 계속을 누르세요."
                : "일시정지했습니다. 계속하면 현재 게시물을 다시 확인합니다.";
            emit();
            return;
          }
          const reason =
            code === "ACCESS_RESTRICTED"
              ? "로그인 후에도 게시물을 열람할 수 없습니다."
              : code === "CAROUSEL_REVIEW"
                ? "첨부물 순서를 끝까지 확인하지 못했습니다."
                : code === "MEDIA_UNAVAILABLE"
                  ? "정상 재생 미디어를 확인하지 못했습니다."
                  : String(code).slice(0, 200);
          await io.outcome(
            post.targets.filter((t) => !done.has(t.id)).map((t) => t.id),
            reason,
            code === "ACCESS_RESTRICTED"
              ? "BROWSER_ACCESS_RESTRICTED"
              : "BROWSER_REVIEW_REQUIRED",
          );
          state.results.push({
            url: post.url,
            status: "review",
            reason,
            count: saved.length,
          });
        }
        state.cursor++;
        emit();
        await io.delay(1800);
      }
      state.status = stop ? "paused" : "completed";
      state.message = stop
        ? "일시정지했습니다."
        : `완료 ${state.results.filter((r) => r.status === "saved").length}개 · 확인 필요 ${state.results.filter((r) => r.status === "review").length}개`;
      emit();
    } catch (error) {
      state.status = "paused";
      state.message = "처리를 멈췄습니다. 연결 상태를 확인한 뒤 계속하세요.";
      emit();
    } finally {
      running = false;
    }
  }
  return {
    get: () => ({ ...state, running }),
    set(posts) {
      if (running) throw Error("일괄 처리를 먼저 일시정지하세요.");
      state = {
        posts,
        cursor: 0,
        results: [],
        status: "ready",
        message: `${posts.length}개 게시물 준비`,
      };
      emit();
    },
    run,
    pause() {
      stop = true;
      state.message = "현재 파일 저장을 마친 뒤 일시정지합니다.";
      emit();
    },
  };
}
module.exports = { createBatch };
