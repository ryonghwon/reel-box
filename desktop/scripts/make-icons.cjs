const fs = require("node:fs"),
  path = require("node:path");
const { execFileSync } = require("node:child_process");
const sharp = require("../../frontend/node_modules/sharp");
const root = path.resolve(__dirname, "../assets");
fs.mkdirSync(root, { recursive: true });
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024"><rect x="60" y="60" width="904" height="904" rx="208" fill="#252728"/><g transform="translate(188 160) scale(27)" fill="#faf9f6"><path fill-rule="evenodd" d="M12 2a7 7 0 0 0-6.7 9H3v8a3 3 0 0 0 3 3h12a3 3 0 0 0 3-3v-8h-2.3A7 7 0 0 0 12 2Zm0 2a1.6 1.6 0 1 1 0 3.2A1.6 1.6 0 0 1 12 4ZM8.5 8.5a1.6 1.6 0 1 1 0 3.2 1.6 1.6 0 0 1 0-3.2Zm7 0a1.6 1.6 0 1 1 0 3.2 1.6 1.6 0 0 1 0-3.2ZM12 8a1 1 0 1 1 0 2 1 1 0 0 1 0-2ZM5 13v6a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-6h-4v2H9v-2H5Z"/></g></svg>`;
fs.writeFileSync(path.join(root, "icon.svg"), svg);
(async () => {
  await sharp(Buffer.from(svg)).png().toFile(path.join(root, "icon.png"));
  const set = path.join(root, "icon.iconset");
  fs.mkdirSync(set, { recursive: true });
  for (const n of [16, 32, 128, 256, 512])
    for (const scale of [1, 2])
      await sharp(Buffer.from(svg))
        .resize(n * scale)
        .png()
        .toFile(
          path.join(set, `icon_${n}x${n}${scale === 2 ? "@2x" : ""}.png`),
        );
  const chunks = [];
  for (const [code, size] of [
    ["ic07", 128],
    ["ic08", 256],
    ["ic09", 512],
    ["ic10", 1024],
  ]) {
    const png = await sharp(Buffer.from(svg)).resize(size).png().toBuffer();
    const head = Buffer.alloc(8);
    head.write(code);
    head.writeUInt32BE(png.length + 8, 4);
    chunks.push(head, png);
  }
  const ih = Buffer.alloc(8);
  ih.write("icns");
  ih.writeUInt32BE(8 + chunks.reduce((n, b) => n + b.length, 0), 4);
  fs.writeFileSync(
    path.join(root, "icon.icns"),
    Buffer.concat([ih, ...chunks]),
  );
  const png = await sharp(Buffer.from(svg)).resize(256).png().toBuffer();
  const h = Buffer.alloc(22);
  h.writeUInt16LE(1, 2);
  h.writeUInt16LE(1, 4);
  h.writeUInt16LE(1, 10);
  h.writeUInt16LE(32, 12);
  h.writeUInt32LE(png.length, 14);
  h.writeUInt32LE(22, 18);
  fs.writeFileSync(path.join(root, "icon.ico"), Buffer.concat([h, png]));
})();
