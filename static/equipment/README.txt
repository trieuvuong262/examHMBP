# Thư mục file cài Agent / UltraViewer (IT deploy)

JustPlayAgent.exe
  - Build: scripts\build-justplay-agent.cmd
  - URL: /thiet-bi/agent/exe/

UltraViewer_setup_vi.exe (tùy chọn, khuyến nghị)
  - Tải bản tiếng Việt từ https://www.ultraviewer.net/vi/download.html
  - Đặt vào thư mục này (hoặc đổi tên UltraViewer_setup_en.exe → dùng URL trong .env)
  - Agent ưu tiên tải từ portal; nếu không có file thì tải từ ultraviewer.net
  - URL: /static/equipment/UltraViewer_setup_en.exe

Deploy VPS: git push hoặc scp các file .exe lên static/equipment/
