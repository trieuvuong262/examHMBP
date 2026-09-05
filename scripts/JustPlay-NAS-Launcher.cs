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
    /// Launcher Công cụ IT (RustDesk Windows/Ubuntu + quét thiết bị).
    /// Logic cài Windows (.ps1) giữ nguyên — chỉ đổi nhãn nút.
    /// </summary>
    internal sealed class NasMainForm : Form
    {
        private readonly string _sourceDir;
        private readonly bool _hasRustdeskWin;
        private readonly bool _hasRustdeskUbuntu;
        private readonly bool _hasEquipmentScan;

        private Label _lblStatus;
        private Button _btnRustdeskWin;
        private Button _btnRustdeskUbuntu;
        private Button _btnEquipment;

        internal NasMainForm(
            string sourceDir,
            string userHint,
            bool hasRustdeskWin,
            bool hasRustdeskUbuntu,
            bool hasEquipmentScan)
        {
            _sourceDir = sourceDir;
            _hasRustdeskWin = hasRustdeskWin;
            _hasRustdeskUbuntu = hasRustdeskUbuntu;
            _hasEquipmentScan = hasEquipmentScan;

            Text = "JustPlay Công cụ IT";
            Font = new Font("Segoe UI", 10F);
            ClientSize = new Size(460, 340);
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
                ? "RustDesk (Windows / Ubuntu 26.04) và gửi cấu hình máy"
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
                Size = new Size(412, 156),
                BackColor = Color.White,
                BorderStyle = BorderStyle.FixedSingle,
            };
            Controls.Add(card);

            card.Controls.Add(MakeLabel("Công cụ IT", 20, 14));

            // Chỉ đổi tên nút — vẫn gọi JustPlay-RustDesk-Setup.ps1 như cũ
            _btnRustdeskWin = MakeActionButton("Cài RustDesk (Windows)", Color.FromArgb(37, 99, 235), 20, 42, 180);
            _btnRustdeskUbuntu = MakeActionButton("Cài RustDesk (Ubuntu)", Color.FromArgb(233, 84, 32), 212, 42, 180);
            _btnEquipment = MakeActionButton("Thêm Cấu hình", Color.FromArgb(5, 150, 105), 20, 96, 372);

            _btnRustdeskWin.Enabled = _hasRustdeskWin;
            _btnRustdeskUbuntu.Enabled = _hasRustdeskUbuntu;
            _btnEquipment.Enabled = _hasEquipmentScan;

            _btnRustdeskWin.Click += async (s, e) => await RunCompanionScriptAsync(
                "JustPlay-RustDesk-Setup.ps1",
                "RustDesk-Setup",
                "Đang cài RustDesk (Windows)...",
                "Hoàn tất RustDesk Windows. Kiểm tra máy trong menu RustDesk trên Portal.");
            _btnRustdeskUbuntu.Click += (s, e) => ShowUbuntuInstallHelp();
            _btnEquipment.Click += async (s, e) => await RunCompanionScriptAsync(
                "JustPlay-Equipment-Scan.ps1",
                "Equipment-Scan",
                "Đang quét cấu hình máy...",
                "Hoàn tất. Kiểm tra thiết bị trong Quản lý thiết bị IT trên Portal.");

            card.Controls.Add(_btnRustdeskWin);
            card.Controls.Add(_btnRustdeskUbuntu);
            card.Controls.Add(_btnEquipment);

            _lblStatus = new Label
            {
                Text = ReadyStatusText(),
                AutoSize = false,
                Size = new Size(412, 40),
                Location = new Point(24, 276),
                ForeColor = Color.FromArgb(100, 116, 139),
            };
            Controls.Add(_lblStatus);
        }

        private string ReadyStatusText()
        {
            if (!_hasRustdeskWin && !_hasRustdeskUbuntu && !_hasEquipmentScan)
            {
                return "Thiếu script IT trong ZIP. Tải lại từ Portal.";
            }
            return "Sẵn sàng.";
        }

        private void ShowUbuntuInstallHelp()
        {
            var shName = "JustPlay-RustDesk-Setup.sh";
            var shPath = Path.Combine(_sourceDir, shName);
            if (!File.Exists(shPath))
            {
                MessageBox.Show(
                    this,
                    "Thiếu file " + shName + ".\nTải lại ZIP từ Portal.",
                    Text,
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning);
                return;
            }

            try
            {
                Process.Start("explorer.exe", "/select,\"" + shPath + "\"");
            }
            catch
            {
            }

            var msg =
                "Cài RustDesk trên Ubuntu 26.04.1 LTS\n\n" +
                "1) Copy file JustPlay-RustDesk-Setup.sh sang máy Ubuntu\n" +
                "2) Mở Terminal tại thư mục chứa file, chạy:\n\n" +
                "   chmod +x JustPlay-RustDesk-Setup.sh\n" +
                "   sudo ./JustPlay-RustDesk-Setup.sh\n\n" +
                "Script sẽ: cài .deb → cấu hình server JustPlay → đặt mật khẩu → đăng ký Portal.\n" +
                "File đã được chọn trong Explorer.";
            MessageBox.Show(this, msg, "Cài RustDesk (Ubuntu)", MessageBoxButtons.OK, MessageBoxIcon.Information);
            _lblStatus.Text = "Đã mở hướng dẫn cài Ubuntu — chạy .sh trên máy Ubuntu 26.04.";
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
            _btnEquipment.Enabled = !busy && _hasEquipmentScan;
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
                        ? "Cần chấp nhận UAC (quyền Administrator).\n\n• Bấm Có khi Windows hỏi\n• Nếu đã bấm Không: chạy lại «Cài RustDesk (Windows)»\n• Hoặc chuột phải JustPlay-RustDesk-Setup.cmd → Run as administrator"
                        : "Tải lại ZIP từ Portal hoặc chạy script bằng quyền Administrator.";
                    if (code == 1223)
                    {
                        hint = "Đã hủy UAC (Không nâng quyền Administrator).\nChạy lại và bấm Có khi Windows hỏi.";
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
            try
            {
                File.Delete(destPs1 + ":Zone.Identifier");
            }
            catch
            {
            }

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
                    if (proc == null)
                    {
                        return 1;
                    }
                    proc.WaitForExit();
                    return proc.ExitCode;
                }
            }
            catch (System.ComponentModel.Win32Exception ex)
            {
                if (ex.NativeErrorCode == 1223)
                {
                    return 1223;
                }
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
                bool hasEquipmentScan;
                ReadBundleMeta(sourceDir, out userHint, out hasRustdeskWin, out hasRustdeskUbuntu, out hasEquipmentScan);

                if (!hasRustdeskWin && !hasRustdeskUbuntu && !hasEquipmentScan)
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
                    hasEquipmentScan));
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
            out bool hasEquipmentScan)
        {
            userHint = "";
            hasRustdeskWin = File.Exists(Path.Combine(sourceDir, "JustPlay-RustDesk-Setup.ps1"));
            hasRustdeskUbuntu = File.Exists(Path.Combine(sourceDir, "JustPlay-RustDesk-Setup.sh"));
            hasEquipmentScan = File.Exists(Path.Combine(sourceDir, "JustPlay-Equipment-Scan.ps1"));
            var cfgPath = Path.Combine(sourceDir, "JustPlay-NAS-Config.json");
            if (!File.Exists(cfgPath))
            {
                return;
            }
            var json = File.ReadAllText(cfgPath);
            var um = Regex.Match(json, "\"portal_username\"\\s*:\\s*\"([^\"]*)\"");
            if (um.Success)
            {
                userHint = um.Groups[1].Value;
            }
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
                hasEquipmentScan = eq.Groups[1].Value == "true" && hasEquipmentScan;
            }
        }

        private static void UnblockDirectory(string dir)
        {
            if (!Directory.Exists(dir))
            {
                return;
            }
            foreach (var file in Directory.GetFiles(dir))
            {
                try
                {
                    File.Delete(file + ":Zone.Identifier");
                }
                catch
                {
                }
            }
        }
    }
}
