# Thư mục file cài Agent / UltraViewer (IT deploy)

JustPlayAgent.exe
  - Build: scripts\build-justplay-agent.cmd
  - URL: /thiet-bi/agent/exe/

UltraViewer_setup_en.exe (tùy chọn, khuyến nghị)
  - Tải từ https://www.ultraviewer.net/en/download.html
  - Đổi tên thành UltraViewer_setup_en.exe và đặt vào thư mục này
  - Agent ưu tiên tải từ portal; nếu không có file thì tải từ ultraviewer.net
  - URL: /static/equipment/UltraViewer_setup_en.exe

Deploy VPS: git push hoặc scp các file .exe lên static/equipment/
