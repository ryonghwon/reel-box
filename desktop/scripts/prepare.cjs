const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { execFileSync } = require("node:child_process");
const desktop = path.resolve(__dirname, ".."),
  repo = path.dirname(desktop),
  work = path.resolve(process.env.REELBOX_BUILD_WORK || path.join(repo, ".build"));
const target = process.argv[2] || `${process.platform}-${process.arch}`;
if (!["darwin-arm64", "win32-x64"].includes(target))
  throw Error("Supported build targets: darwin-arm64, win32-x64");
const mac = target === "darwin-arm64",
  out = path.join(desktop, "payload", mac ? "mac-arm64" : "win-x64"),
  cache = path.join(work, "desktop-downloads");
fs.mkdirSync(cache, { recursive: true });
const env = {
  ...process.env,
  UV_CACHE_DIR: path.join(work, "uv-cache"),
  npm_config_cache: path.join(work, "npm-cache"),
};
const run = (cmd, args, options = {}) =>
  execFileSync(cmd, args, { stdio: "inherit", env, ...options });
const hash = (p) =>
  crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
async function download(url, file, expected) {
  if (!fs.existsSync(file)) {
    const r = await fetch(url);
    if (!r.ok) throw Error(`${r.status} ${url}`);
    fs.writeFileSync(file, Buffer.from(await r.arrayBuffer()));
  }
  if (expected && hash(file) !== expected) {
    fs.rmSync(file);
    throw Error(`Checksum mismatch ${file}`);
  }
  return file;
}
function find(dir, name) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isFile() && entry.name === name) return p;
    if (entry.isDirectory()) {
      const got = find(p, name);
      if (got) return got;
    }
  }
}
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const pythonSource = path.join(
    work,
    "python-runtimes",
    `cpython-3.12.14-${mac ? "macos-aarch64" : "windows-x86_64"}-none`,
  );
  if (!fs.existsSync(pythonSource))
    throw Error(
      `Install Python 3.12.14 for ${target} into work/python-runtimes first.`,
    );
  const py = path.join(out, "python");
  if (!fs.existsSync(py))
    fs.cpSync(pythonSource, py, { recursive: true, verbatimSymlinks: true });
  // uv adds a host-only alias when staging a foreign runtime. Windows uses python.exe.
  if (!mac) {
    const alias = path.join(py, "python");
    if (fs.existsSync(alias) || fs.lstatSync(alias, { throwIfNoEntry: false }))
      fs.rmSync(alias);
  }
  const site = path.join(
    py,
    mac ? "lib/python3.12/site-packages" : "Lib/site-packages",
  );
  run("uv", [
    "pip",
    "install",
    "--python",
    path.join(
      work,
      "python-runtimes/cpython-3.12.14-macos-aarch64-none/bin/python3",
    ),
    "--python-version",
    "3.12",
    "--python-platform",
    mac ? "aarch64-apple-darwin" : "x86_64-pc-windows-msvc",
    "--target",
    site,
    "--only-binary",
    ":all:",
    "-r",
    path.join(repo, "backend/requirements-desktop.lock.txt"),
  ]);
  const bin = path.join(out, "bin");
  fs.mkdirSync(bin, { recursive: true });
  const packages = mac
    ? {
        "@ffmpeg-installer/darwin-arm64": "4.1.5",
        "@ffprobe-installer/darwin-arm64": "5.0.1",
      }
    : {};
  const manifest = { target, python: "3.12.14", packages: [], node: null };
  for (const [name, version] of Object.entries(packages)) {
    const packed = JSON.parse(
      execFileSync(
        "npm",
        ["pack", `${name}@${version}`, "--json", "--pack-destination", cache],
        { env, encoding: "utf8" },
      ),
    )[0];
    const tgz = path.join(cache, packed.filename);
    const unpack = path.join(cache, name.replaceAll("/", "-"));
    fs.mkdirSync(unpack, { recursive: true });
    run("tar", ["-xzf", tgz, "-C", unpack]);
    const binary = name.includes("ffprobe") ? "ffprobe" : "ffmpeg";
    const filename = binary + (mac ? "" : ".exe");
    const from = find(unpack, filename);
    if (!from) throw Error("Missing " + filename);
    fs.copyFileSync(from, path.join(bin, filename));
    if (mac) fs.chmodSync(path.join(bin, filename), 0o755);
    manifest.packages.push({
      name,
      version,
      integrity: packed.integrity,
      sha256: hash(tgz),
    });
    const license = find(unpack, "LICENSE") || find(unpack, "LICENSE.txt");
    if (license)
      fs.copyFileSync(license, path.join(out, `${binary}-LICENSE.txt`));
  }
  if (!mac) {
    const source =
      "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip";
    const checksum =
      "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba";
    const archive = await download(
      source,
      path.join(cache, "ffmpeg-9.0.2-win-x64.zip"),
      checksum,
    );
    const unpack = path.join(cache, "ffmpeg-9.0.2-win-x64");
    fs.mkdirSync(unpack, { recursive: true });
    run("/usr/bin/python3", ["-m", "zipfile", "-e", archive, unpack]);
    for (const name of ["ffmpeg.exe", "ffprobe.exe"])
      fs.copyFileSync(find(unpack, name), path.join(bin, name));
    for (const name of ["LICENSE", "LICENSE.txt", "README.txt"]) {
      const license = find(unpack, name);
      if (license) fs.copyFileSync(license, path.join(out, "ffmpeg-" + name));
    }
    manifest.ffmpeg = { version: "9.0.2", source, sha256: checksum };
  }
  const versions = await (
    await fetch("https://nodejs.org/dist/index.json")
  ).json();
  const version = versions.find((v) => v.version.startsWith("v24.")).version;
  const filename = mac
    ? `node-${version}-darwin-arm64.tar.gz`
    : `node-${version}-win-x64.zip`;
  const base = `https://nodejs.org/dist/${version}/`;
  const sums = await (await fetch(base + "SHASUMS256.txt")).text();
  const line = sums.split("\n").find((x) => x.endsWith("  " + filename));
  if (!line) throw Error("Missing Node checksum");
  const expected = line.split(/\s+/)[0];
  const archive = await download(
    base + filename,
    path.join(cache, filename),
    expected,
  );
  const unpack = path.join(cache, "node-" + target);
  fs.mkdirSync(unpack, { recursive: true });
  if (mac) run("tar", ["-xzf", archive, "-C", unpack]);
  else run("/usr/bin/python3", ["-m", "zipfile", "-e", archive, unpack]);
  const nodeName = mac ? "node" : "node.exe";
  fs.copyFileSync(find(unpack, nodeName), path.join(bin, nodeName));
  if (mac) fs.chmodSync(path.join(bin, nodeName), 0o755);
  const nodeLicense = find(unpack, "LICENSE");
  if (nodeLicense)
    fs.copyFileSync(nodeLicense, path.join(out, "node-LICENSE.txt"));
  manifest.node = { version, source: base + filename, sha256: expected };
  fs.writeFileSync(
    path.join(out, "manifest.json"),
    JSON.stringify(manifest, null, 2),
  );
  console.log(`Prepared self-contained ${target} runtime: ${out}`);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
