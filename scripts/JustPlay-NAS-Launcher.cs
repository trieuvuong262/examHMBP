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
    /// Launcher Công cụ IT — chỉ Windows (.exe). Ubuntu dùng gói .deb riêng.
    /// </summary>
    internal sealed class NasMainForm : Form
    {
        private readonly string _sourceDir;
        private readonly bool _hasRustdesk;
        private readonly bool _hasEquipment;
        private readonly bool _hasRaidrive;
        private readonly string _raidriveUrl;

        private Label _lblStatus;
        private Button _btnRustdesk;
        private Button _btnEquipment;
        private Button _btnRaidrive;

        internal NasMainForm(
            string sourceDir,
            string userHint,
            bool hasRustdesk,
            bool hasEquipment,
            bool hasRaidrive,
            string raidriveUrl)
        {
            _sourceDir = sourceDir;
            _hasRustdesk = hasRustdesk;
            _hasEquipment = hasEquipment;
            _hasRaidrive = hasRaidrive;
            _raidriveUrl = raidriveUrl ?? "";

            Text = "JustPlay Công cụ IT (Windows)";
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
                Text = "Công cụ IT — Windows",
                Font = new Font("Segoe UI", 16F, FontStyle.Bold),
                ForeColor = Color.White,
                AutoSize = true,
                Location = new Point(24, 16),
            };
            header.Controls.Add(lblTitle);

            var subText = string.IsNullOrEmpty(userHint)
                ? "RustDesk · Cấu hình máy · RaiDrive (.exe)"
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
                Size = new Size(412, 168),
                BackColor = Color.White,
                BorderStyle = BorderStyle.FixedSingle,
            };
            Controls.Add(card);

            card.Controls.Add(MakeLabel("Cài đặt Windows", 20, 14));

            _btnRustdesk = MakeActionButton("Cài RustDesk", Color.FromArgb(37, 99, 235), 20, 42, 372);
            _btnEquipment = MakeActionButton("Thêm Cấu hình", Color.FromArgb(5, 150, 105), 20, 90, 372);
            _btnRaidrive = MakeActionButton("Cài RaiDrive", Color.FromArgb(79, 70, 229), 20, 138, 372);

            _btnRustdesk.Enabled = _hasRustdesk;
            _btnEquipment.Enabled = _hasEquipment;
            _btnRaidrive.Enabled = _hasRaidrive;

            _btnRustdesk.Click += async (s, e) => await RunCompanionScriptAsync(
                "JustPlay-RustDesk-Setup.ps1",
                "RustDesk-Setup",
                "Đang cài RustDesk...",
                "Hoàn tất RustDesk. Kiểm tra máy trong menu RustDesk trên Portal.");
            _btnEquipment.Click += async (s, e) => await RunCompanionScriptAsync(
                "JustPlay-Equipment-Scan.ps1",
                "Equipment-Scan",
                "Đang quét cấu hình máy...",
                "Hoàn tất. Kiểm tra thiết bị trong Quản lý thiết bị IT trên Portal.");
            _btnRaidrive.Click += (s, e) => OpenRaidrive();

            card.Controls.Add(_btnRustdesk);
            card.Controls.Add(_btnEquipment);
            card.Controls.Add(_btnRaidrive);

            _lblStatus = new Label
            {
                Text = ReadyStatusText(),
                AutoSize = false,
                Size = new Size(412, 36),
                Location = new Point(24, 288),
                ForeColor = Color.FromArgb(100, 116, 139),
            };
            Controls.Add(_lblStatus);
        }

        private string ReadyStatusText()
        {
            if (!_hasRustdesk && !_hasEquipment && !_hasRaidrive)
            {
                return "Thiếu script Windows trong ZIP. Tải lại từ Portal.";
            }
            return "Sẵn sàng (Windows). Ubuntu: tải gói .deb riêng trên Portal.";
        }

        private void OpenRaidrive()
        {
            if (string.IsNullOrWhiteSpace(_raidriveUrl))
            {
                MessageBox.Show(
                    this,
                    "Chưa có URL tải RaiDrive trên Portal.\nLiên hệ IT.",
                    Text,
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning);
                return;
            }
            try
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = _raidriveUrl,
                    UseShellExecute = true,
                });
                _lblStatus.Text = "Đã mở tải RaiDrive (.exe) trên trình duyệt.";
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, ex.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
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
            _btnRustdesk.Enabled = !busy && _hasRustdesk;
            _btnEquipment.Enabled = !busy && _hasEquipment;
            _btnRaidrive.Enabled = !busy && _hasRaidrive;
            _lblStatus.Text = status;
            Cursor = busy ? Cursors.WaitCursor : Cursors.Default;
            Application.DoEvents();
        }

        private async Task RunCompanionScriptAsync(string fileName, string workSubDir, string busyText, string successText)
        {
            var sourcePs1 = Path.Combine(_sourceDir, fileName);
            if (!File.Exists(sourcePs1))
            {
                MessageBox.Show(this, "Thiếu file " + fileName + ".\nTải lại ZIP Windows từ Portal.", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
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
                        ? "Cần chấp nhận UAC (Administrator).\nBấm Có khi Windows hỏi."
                        : "Chạy lại với quyền Administrator.";
                    if (code == 1223)
                    {
                        hint = "Đã hủy UAC. Chạy lại và bấm Có.";
                    }
                    MessageBox.Show(this, "Thao tác thất bại (mã " + code + ").\n\n" + hint, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
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
                bool hasRustdesk;
                bool hasEquipment;
                bool hasRaidrive;
                string raidriveUrl;
                ReadBundleMeta(sourceDir, out userHint, out hasRustdesk, out hasEquipment, out hasRaidrive, out raidriveUrl);

                if (!hasRustdesk && !hasEquipment && !hasRaidrive)
                {
                    MessageBox.Show(
                        "Thiếu script Windows trong thư mục cài đặt.\nTải ZIP Windows từ Portal.",
                        "JustPlay Công cụ IT",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                    return 1;
                }

                Application.Run(new NasMainForm(
                    sourceDir,
                    userHint,
                    hasRustdesk,
                    hasEquipment,
                    hasRaidrive,
                    raidriveUrl));
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
            out bool hasRustdesk,
            out bool hasEquipment,
            out bool hasRaidrive,
            out string raidriveUrl)
        {
            userHint = "";
            raidriveUrl = "";
            hasRustdesk = File.Exists(Path.Combine(sourceDir, "JustPlay-RustDesk-Setup.ps1"));
            hasEquipment = File.Exists(Path.Combine(sourceDir, "JustPlay-Equipment-Scan.ps1"));
            hasRaidrive = false;

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
                hasRustdesk = rd.Groups[1].Value == "true" && hasRustdesk;
            }
            var eq = Regex.Match(json, "\"has_equipment_scan\"\\s*:\\s*(true|false)");
            if (eq.Success)
            {
                hasEquipment = eq.Groups[1].Value == "true" && hasEquipment;
            }
            var url = Regex.Match(json, "\"raidrive_download_url\"\\s*:\\s*\"([^\"]*)\"");
            if (url.Success)
            {
                raidriveUrl = url.Groups[1].Value.Replace("\\/", "/");
                hasRaidrive = !string.IsNullOrWhiteSpace(raidriveUrl);
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
