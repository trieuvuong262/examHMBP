using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace JustPlay.NasLauncher
{
    /// <summary>
    /// Launcher Công cụ IT: RustDesk, Thêm cấu hình, RaiDrive (Win/Ubuntu).
    /// </summary>
    internal sealed class NasMainForm : Form
    {
        private readonly string _sourceDir;
        private readonly bool _hasRustdeskWin;
        private readonly bool _hasRustdeskUbuntu;
        private readonly bool _hasEquipmentWin;
        private readonly bool _hasEquipmentUbuntu;
        private readonly bool _hasRaidriveWin;
        private readonly bool _hasRaidriveUbuntu;
        private readonly string _raidriveWinUrl;
        private readonly string _raidriveLinuxPage;

        private Label _lblStatus;
        private Button _btnRustdeskWin;
        private Button _btnRustdeskUbuntu;
        private Button _btnEquipmentWin;
        private Button _btnEquipmentUbuntu;
        private Button _btnRaidriveWin;
        private Button _btnRaidriveUbuntu;

        internal NasMainForm(
            string sourceDir,
            string userHint,
            bool hasRustdeskWin,
            bool hasRustdeskUbuntu,
            bool hasEquipmentWin,
            bool hasEquipmentUbuntu,
            bool hasRaidriveWin,
            bool hasRaidriveUbuntu,
            string raidriveWinUrl,
            string raidriveLinuxPage)
        {
            _sourceDir = sourceDir;
            _hasRustdeskWin = hasRustdeskWin;
            _hasRustdeskUbuntu = hasRustdeskUbuntu;
            _hasEquipmentWin = hasEquipmentWin;
            _hasEquipmentUbuntu = hasEquipmentUbuntu;
            _hasRaidriveWin = hasRaidriveWin;
            _hasRaidriveUbuntu = hasRaidriveUbuntu;
            _raidriveWinUrl = raidriveWinUrl ?? "";
            _raidriveLinuxPage = string.IsNullOrEmpty(raidriveLinuxPage)
                ? "https://www.raidrive.com/download/linux"
                : raidriveLinuxPage;

            Text = "JustPlay Công cụ IT";
            Font = new Font("Segoe UI", 10F);
            ClientSize = new Size(460, 460);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Color.FromArgb(248, 250, 252);

            var header = new Panel
            {
                Dock = DockStyle.Top,
                Height = 88,
                BackColor = Color.FromArgb(220, 38, 38),
            };
            Controls.Add(header);

            var lblTitle = new Label
            {
                Text = "Công cụ IT JustPlay",
                Font = new Font("Segoe UI", 16F, FontStyle.Bold),
                ForeColor = Color.White,
                AutoSize = true,
                Location = new Point(24, 16),
            };
            header.Controls.Add(lblTitle);

            var subText = string.IsNullOrEmpty(userHint)
                ? "RustDesk · Cấu hình máy · RaiDrive"
                : "Tài khoản: " + userHint;
            var lblSub = new Label
            {
                Text = subText,
                Font = new Font("Segoe UI", 9F),
                ForeColor = Color.FromArgb(254, 226, 226),
                AutoSize = false,
                Size = new Size(410, 32),
                Location = new Point(26, 50),
            };
            header.Controls.Add(lblSub);

            var card = new Panel
            {
                Location = new Point(24, 104),
                Size = new Size(412, 276),
                BackColor = Color.White,
                BorderStyle = BorderStyle.FixedSingle,
            };
            Controls.Add(card);

            card.Controls.Add(MakeLabel("Công cụ IT", 20, 12));

            _btnRustdeskWin = MakeActionButton("Cài RustDesk (Windows)", Color.FromArgb(37, 99, 235), 20, 38, 180);
            _btnRustdeskUbuntu = MakeActionButton("Cài RustDesk (Ubuntu)", Color.FromArgb(233, 84, 32), 212, 38, 180);
            // Chỉ đổi tên nút Windows — vẫn chạy JustPlay-Equipment-Scan.ps1 như cũ
            _btnEquipmentWin = MakeActionButton("Thêm Cấu hình (Windows)", Color.FromArgb(5, 150, 105), 20, 90, 180);
            _btnEquipmentUbuntu = MakeActionButton("Thêm Cấu hình (Ubuntu)", Color.FromArgb(16, 185, 129), 212, 90, 180);
            _btnRaidriveWin = MakeActionButton("Cài RaiDrive (Windows)", Color.FromArgb(79, 70, 229), 20, 142, 180);
            _btnRaidriveUbuntu = MakeActionButton("Cài RaiDrive (Ubuntu)", Color.FromArgb(124, 58, 237), 212, 142, 180);

            _btnRustdeskWin.Enabled = _hasRustdeskWin;
            _btnRustdeskUbuntu.Enabled = _hasRustdeskUbuntu;
            _btnEquipmentWin.Enabled = _hasEquipmentWin;
            _btnEquipmentUbuntu.Enabled = _hasEquipmentUbuntu;
            _btnRaidriveWin.Enabled = _hasRaidriveWin;
            _btnRaidriveUbuntu.Enabled = _hasRaidriveUbuntu;

            _btnRustdeskWin.Click += async (s, e) => await RunCompanionScriptAsync(
                "JustPlay-RustDesk-Setup.ps1",
                "RustDesk-Setup",
                "Đang cài RustDesk (Windows)...",
                "Hoàn tất RustDesk Windows. Kiểm tra máy trong menu RustDesk trên Portal.");
            _btnRustdeskUbuntu.Click += (s, e) => ShowUbuntuRustDeskHelp();
            _btnEquipmentWin.Click += async (s, e) => await RunCompanionScriptAsync(
                "JustPlay-Equipment-Scan.ps1",
                "Equipment-Scan",
                "Đang quét cấu hình máy (Windows)...",
                "Hoàn tất. Kiểm tra thiết bị trong Quản lý thiết bị IT trên Portal.");
            _btnEquipmentUbuntu.Click += (s, e) => ShowUbuntuEquipmentHelp();
            _btnRaidriveWin.Click += (s, e) => OpenRaidriveWindows();
            _btnRaidriveUbuntu.Click += (s, e) => ShowUbuntuRaidriveHelp();

            card.Controls.Add(_btnRustdeskWin);
            card.Controls.Add(_btnRustdeskUbuntu);
            card.Controls.Add(_btnEquipmentWin);
            card.Controls.Add(_btnEquipmentUbuntu);
            card.Controls.Add(_btnRaidriveWin);
            card.Controls.Add(_btnRaidriveUbuntu);

            var lblRdHint = new Label
            {
                Text = "Ubuntu: copy file .sh sang máy → chmod +x → chạy (sudo nếu cần).",
                Font = new Font("Segoe UI", 8F),
                ForeColor = Color.FromArgb(100, 116, 139),
                AutoSize = false,
                Size = new Size(372, 36),
                Location = new Point(20, 196),
            };
            card.Controls.Add(lblRdHint);

            _lblStatus = new Label
            {
                Text = ReadyStatusText(),
                AutoSize = false,
                Size = new Size(412, 40),
                Location = new Point(24, 396),
                ForeColor = Color.FromArgb(100, 116, 139),
            };
            Controls.Add(_lblStatus);
        }

        private string ReadyStatusText()
        {
            if (!_hasRustdeskWin && !_hasRustdeskUbuntu && !_hasEquipmentWin && !_hasEquipmentUbuntu && !_hasRaidriveWin && !_hasRaidriveUbuntu)
            {
                return "Thiếu script IT trong ZIP. Tải lại từ Portal.";
            }
            return "Sẵn sàng.";
        }

        private void OpenRaidriveWindows()
        {
            if (string.IsNullOrWhiteSpace(_raidriveWinUrl))
            {
                MessageBox.Show(
                    this,
                    "Chưa có URL tải RaiDrive Windows trên Portal.\nLiên hệ IT hoặc mở trang Tải bộ cài.",
                    Text,
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning);
                return;
            }
            try
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = _raidriveWinUrl,
                    UseShellExecute = true,
                });
                _lblStatus.Text = "Đã mở tải RaiDrive (Windows) trên trình duyệt.";
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, ex.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void ShowUbuntuRustDeskHelp()
        {
            ShowUbuntuScriptHelp(
                "JustPlay-RustDesk-Setup.sh",
                "Cài RustDesk (Ubuntu)",
                "Cài RustDesk trên Ubuntu 26.04.1 LTS\n\n" +
                "1) Copy file JustPlay-RustDesk-Setup.sh sang máy Ubuntu\n" +
                "2) Chạy:\n\n" +
                "   chmod +x JustPlay-RustDesk-Setup.sh\n" +
                "   sudo ./JustPlay-RustDesk-Setup.sh");
        }

        private void ShowUbuntuEquipmentHelp()
        {
            ShowUbuntuScriptHelp(
                "JustPlay-Equipment-Scan.sh",
                "Thêm Cấu hình (Ubuntu)",
                "Quét cấu hình máy Ubuntu → gửi lên Portal\n" +
                "(cùng mục đích với Thêm Cấu hình Windows)\n\n" +
                "1) Copy JustPlay-Equipment-Scan.sh sang máy Ubuntu\n" +
                "2) Chạy (không bắt buộc sudo):\n\n" +
                "   chmod +x JustPlay-Equipment-Scan.sh\n" +
                "   ./JustPlay-Equipment-Scan.sh\n\n" +
                "Script đọc MAC/IP/hostname rồi đăng ký thiết bị IT trên Portal.");
        }

        private void ShowUbuntuRaidriveHelp()
        {
            var shName = "JustPlay-RaiDrive-Setup.sh";
            var shPath = Path.Combine(_sourceDir, shName);
            if (File.Exists(shPath))
            {
                try { Process.Start("explorer.exe", "/select,\"" + shPath + "\""); } catch { }
            }
            try
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = _raidriveLinuxPage,
                    UseShellExecute = true,
                });
            }
            catch
            {
            }

            var msg =
                "Cài RaiDrive CLI trên Ubuntu 26.04\n\n" +
                "Cách 1 — script JustPlay:\n" +
                "   chmod +x JustPlay-RaiDrive-Setup.sh\n" +
                "   sudo ./JustPlay-RaiDrive-Setup.sh\n\n" +
                "Cách 2 — trang chính thức (đã mở trình duyệt):\n" +
                "   " + _raidriveLinuxPage + "\n" +
                "   Tải .deb → sudo apt install -fy ./raidrive-*.deb";
            MessageBox.Show(this, msg, "Cài RaiDrive (Ubuntu)", MessageBoxButtons.OK, MessageBoxIcon.Information);
            _lblStatus.Text = "Đã mở hướng dẫn RaiDrive Ubuntu.";
        }

        private void ShowUbuntuScriptHelp(string shName, string title, string body)
        {
            var shPath = Path.Combine(_sourceDir, shName);
            if (!File.Exists(shPath))
            {
                MessageBox.Show(this, "Thiếu file " + shName + ".\nTải lại ZIP từ Portal.", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            try { Process.Start("explorer.exe", "/select,\"" + shPath + "\""); } catch { }
            MessageBox.Show(this, body + "\n\nFile đã được chọn trong Explorer.", title, MessageBoxButtons.OK, MessageBoxIcon.Information);
            _lblStatus.Text = "Đã mở hướng dẫn " + title + ".";
        }

        private static Label MakeLabel(string text, int x, int y)
        {
            return new Label
            {
                Text = text,
                Font = new Font("Segoe UI", 9F, FontStyle.Bold),
                ForeColor = Color.FromArgb(15, 23, 42),
                AutoSize = true,
                Location = new Point(x, y),
            };
        }

        private Button MakeActionButton(string text, Color bg, int x, int y, int width)
        {
            var btn = new Button
            {
                Text = text,
                FlatStyle = FlatStyle.Flat,
                BackColor = bg,
                ForeColor = Color.White,
                Font = new Font("Segoe UI", 9F, FontStyle.Bold),
                Size = new Size(width, 36),
                Location = new Point(x, y),
                Cursor = Cursors.Hand,
            };
            btn.FlatAppearance.BorderSize = 0;
            btn.Region = Region.FromHrgn(NativeMethods.CreateRoundRectRgn(0, 0, btn.Width, btn.Height, 8, 8));
            return btn;
        }

        private void SetBusy(bool busy, string status)
        {
            _btnRustdeskWin.Enabled = !busy && _hasRustdeskWin;
            _btnRustdeskUbuntu.Enabled = !busy && _hasRustdeskUbuntu;
            _btnEquipmentWin.Enabled = !busy && _hasEquipmentWin;
            _btnEquipmentUbuntu.Enabled = !busy && _hasEquipmentUbuntu;
            _btnRaidriveWin.Enabled = !busy && _hasRaidriveWin;
            _btnRaidriveUbuntu.Enabled = !busy && _hasRaidriveUbuntu;
            _lblStatus.Text = status;
            Cursor = busy ? Cursors.WaitCursor : Cursors.Default;
            Application.DoEvents();
        }

        private async Task RunCompanionScriptAsync(string fileName, string workSubDir, string busyText, string successText)
        {
            var sourcePs1 = Path.Combine(_sourceDir, fileName);
            if (!File.Exists(sourcePs1))
            {
                MessageBox.Show(this, "Thiếu file " + fileName + ".\nTải lại ZIP từ Portal.", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            SetBusy(true, busyText);
            try
            {
                var code = await Task.Run(() => RunCompanionScript(fileName, workSubDir)).ConfigureAwait(true);
                if (code == 0)
                {
                    _lblStatus.Text = successText;
                    MessageBox.Show(this, successText, Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
                else
                {
                    var hint = fileName.IndexOf("RustDesk", StringComparison.OrdinalIgnoreCase) >= 0
                        ? "Cần chấp nhận UAC (quyền Administrator).\n\n• Bấm Có khi Windows hỏi\n• Nếu đã bấm Không: chạy lại «Cài RustDesk (Windows)»"
                        : "Tải lại ZIP từ Portal hoặc chạy script bằng quyền Administrator.";
                    if (code == 1223)
                    {
                        hint = "Đã hủy UAC. Chạy lại và bấm Có khi Windows hỏi.";
                    }
                    MessageBox.Show(this, "Thao tác thất bại (mã lỗi " + code + ").\n\n" + hint, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    _lblStatus.Text = "Thao tác thất bại.";
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, ex.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
                _lblStatus.Text = ex.Message;
            }
            finally
            {
                SetBusy(false, _lblStatus.Text);
            }
        }

        private int RunCompanionScript(string fileName, string workSubDir)
        {
            var sourcePs1 = Path.Combine(_sourceDir, fileName);
            var workDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "JustPlay",
                workSubDir);
            Directory.CreateDirectory(workDir);
            var destPs1 = Path.Combine(workDir, fileName);
            File.Copy(sourcePs1, destPs1, true);
            try { File.Delete(destPs1 + ":Zone.Identifier"); } catch { }

            var args = "-NoProfile -ExecutionPolicy Bypass -File \"" + destPs1 + "\"";
            if (fileName.IndexOf("RustDesk", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                args += " -Elevated";
            }

            var psi = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = args,
                WorkingDirectory = workDir,
                UseShellExecute = true,
                Verb = "runas",
            };
            try
            {
                using (var proc = Process.Start(psi))
                {
                    if (proc == null) { return 1; }
                    proc.WaitForExit();
                    return proc.ExitCode;
                }
            }
            catch (System.ComponentModel.Win32Exception ex)
            {
                if (ex.NativeErrorCode == 1223) { return 1223; }
                throw;
            }
        }
    }

    internal static class NativeMethods
    {
        [System.Runtime.InteropServices.DllImport("gdi32.dll")]
        internal static extern IntPtr CreateRoundRectRgn(int x1, int y1, int x2, int y2, int cx, int cy);
    }

    internal static class Program
    {
        [STAThread]
        private static int Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            try
            {
                var sourceDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\', '/');
                UnblockDirectory(sourceDir);

                string userHint;
                bool hasRustdeskWin;
                bool hasRustdeskUbuntu;
                bool hasEquipmentWin;
                bool hasEquipmentUbuntu;
                bool hasRaidriveWin;
                bool hasRaidriveUbuntu;
                string raidriveWinUrl;
                string raidriveLinuxPage;
                ReadBundleMeta(
                    sourceDir,
                    out userHint,
                    out hasRustdeskWin,
                    out hasRustdeskUbuntu,
                    out hasEquipmentWin,
                    out hasEquipmentUbuntu,
                    out hasRaidriveWin,
                    out hasRaidriveUbuntu,
                    out raidriveWinUrl,
                    out raidriveLinuxPage);

                if (!hasRustdeskWin && !hasRustdeskUbuntu && !hasEquipmentWin && !hasEquipmentUbuntu && !hasRaidriveWin && !hasRaidriveUbuntu)
                {
                    MessageBox.Show(
                        "Thiếu script Công cụ IT trong thư mục cài đặt.\nTải lại ZIP từ Portal và giải nén đủ file.",
                        "JustPlay Công cụ IT",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                    return 1;
                }

                Application.Run(new NasMainForm(
                    sourceDir,
                    userHint,
                    hasRustdeskWin,
                    hasRustdeskUbuntu,
                    hasEquipmentWin,
                    hasEquipmentUbuntu,
                    hasRaidriveWin,
                    hasRaidriveUbuntu,
                    raidriveWinUrl,
                    raidriveLinuxPage));
                return 0;
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message, "JustPlay Công cụ IT", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }

        private static void ReadBundleMeta(
            string sourceDir,
            out string userHint,
            out bool hasRustdeskWin,
            out bool hasRustdeskUbuntu,
            out bool hasEquipmentWin,
            out bool hasEquipmentUbuntu,
            out bool hasRaidriveWin,
            out bool hasRaidriveUbuntu,
            out string raidriveWinUrl,
            out string raidriveLinuxPage)
        {
            userHint = "";
            raidriveWinUrl = "";
            raidriveLinuxPage = "https://www.raidrive.com/download/linux";
            hasRustdeskWin = File.Exists(Path.Combine(sourceDir, "JustPlay-RustDesk-Setup.ps1"));
            hasRustdeskUbuntu = File.Exists(Path.Combine(sourceDir, "JustPlay-RustDesk-Setup.sh"));
            hasEquipmentWin = File.Exists(Path.Combine(sourceDir, "JustPlay-Equipment-Scan.ps1"));
            hasEquipmentUbuntu = File.Exists(Path.Combine(sourceDir, "JustPlay-Equipment-Scan.sh"));
            hasRaidriveUbuntu = File.Exists(Path.Combine(sourceDir, "JustPlay-RaiDrive-Setup.sh"));
            hasRaidriveWin = false;

            var cfgPath = Path.Combine(sourceDir, "JustPlay-NAS-Config.json");
            if (!File.Exists(cfgPath))
            {
                return;
            }
            var json = File.ReadAllText(cfgPath);
            var um = Regex.Match(json, "\"portal_username\"\\s*:\\s*\"([^\"]*)\"");
            if (um.Success) { userHint = um.Groups[1].Value; }

            var rd = Regex.Match(json, "\"has_rustdesk\"\\s*:\\s*(true|false)");
            if (rd.Success)
            {
                var flag = rd.Groups[1].Value == "true";
                hasRustdeskWin = flag && hasRustdeskWin;
                hasRustdeskUbuntu = flag && hasRustdeskUbuntu;
            }
            var eq = Regex.Match(json, "\"has_equipment_scan\"\\s*:\\s*(true|false)");
            if (eq.Success)
            {
                var flag = eq.Groups[1].Value == "true";
                hasEquipmentWin = flag && hasEquipmentWin;
                hasEquipmentUbuntu = flag && hasEquipmentUbuntu;
            }

            var url = Regex.Match(json, "\"raidrive_download_url\"\\s*:\\s*\"([^\"]*)\"");
            if (url.Success)
            {
                raidriveWinUrl = url.Groups[1].Value.Replace("\\/", "/");
                hasRaidriveWin = !string.IsNullOrWhiteSpace(raidriveWinUrl);
            }
            var page = Regex.Match(json, "\"raidrive_linux_page\"\\s*:\\s*\"([^\"]*)\"");
            if (page.Success && !string.IsNullOrWhiteSpace(page.Groups[1].Value))
            {
                raidriveLinuxPage = page.Groups[1].Value.Replace("\\/", "/");
            }
            var hasRd = Regex.Match(json, "\"has_raidrive\"\\s*:\\s*(true|false)");
            if (hasRd.Success && hasRd.Groups[1].Value == "false")
            {
                hasRaidriveWin = false;
                hasRaidriveUbuntu = false;
            }
        }

        private static void UnblockDirectory(string dir)
        {
            if (!Directory.Exists(dir)) { return; }
            foreach (var file in Directory.GetFiles(dir))
            {
                try { File.Delete(file + ":Zone.Identifier"); } catch { }
            }
        }
    }
}
