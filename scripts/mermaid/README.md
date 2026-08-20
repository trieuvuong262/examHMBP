# Xuất sơ đồ Mermaid ra SVG

Pipeline dùng để tạo `docs/diagrams/svg/` từ các file Markdown trong
`docs/diagrams/class-diagram/`.

## Cài đặt (một lần)

`mermaid-cli` kéo theo Chromium nên không đưa vào repo. Cài ra ngoài thư mục dự án:

```bash
mkdir -p ../.tooling/mermaid && cd ../.tooling/mermaid
npm init -y && npm install @mermaid-js/mermaid-cli
```

## Sinh sơ đồ

```bash
# 1) Markdown class diagram từ Django models (chạy trong container web)
docker compose run --rm --no-deps -v /opt/portaljustplay:/app web \
  python scripts/gen_class_diagram.py

# 2) Markdown -> SVG
node scripts/mermaid/render.mjs docs/diagrams/class-diagram docs/diagrams/svg

# 3) Gán width/height tuyệt đối để nhúng được vào Word / Inkscape
node scripts/mermaid/fix-svg-size.mjs docs/diagrams/svg
```

`render.mjs` tự tìm `mermaid-cli` bằng cách đi ngược cây thư mục; nếu cài ở nơi khác
thì đặt biến môi trường `MMDC_CLI` trỏ tới `node_modules/@mermaid-js/mermaid-cli/src/cli.js`.

`mermaid.config.json` nâng `maxTextSize` / `maxEdges` vì sơ đồ `san_xuat` (89 model)
vượt xa giới hạn mặc định của Mermaid.
