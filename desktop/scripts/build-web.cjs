const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const desktop = path.resolve(__dirname, ".."),
  source = path.resolve(desktop, "../frontend"),
  stage = path.join(desktop, ".web-build");
fs.rmSync(stage, { recursive: true, force: true });
fs.mkdirSync(stage, { recursive: true });
fs.cpSync(path.join(source, "app"), path.join(stage, "app"), {
  recursive: true,
  filter: (p) => p !== path.join(source, "app", "api"),
});
for (const name of ["package.json", "tsconfig.json", "next-env.d.ts"])
  fs.copyFileSync(path.join(source, name), path.join(stage, name));
fs.writeFileSync(
  path.join(stage, "next.config.ts"),
  `export default ${JSON.stringify({output:"export",images:{unoptimized:true},poweredByHeader:false,turbopack:{root:path.dirname(desktop)}})};\n`,
);
fs.symlinkSync(
  path.join(source, "node_modules"),
  path.join(stage, "node_modules"),
  "junction",
);
execFileSync(
  process.execPath,
  [path.join(source, "node_modules/next/dist/bin/next"), "build"],
  {
    cwd: stage,
    stdio: "inherit",
    env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" },
  },
);
fs.rmSync(path.join(desktop, "web"), { recursive: true, force: true });
fs.cpSync(path.join(stage, "out"), path.join(desktop, "web"), {
  recursive: true,
});
