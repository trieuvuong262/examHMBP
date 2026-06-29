using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace JustPlay.NasLauncher
{
    internal sealed class PsRunResult
    {
        internal int ExitCode { get; set; }
        internal string Stdout { get; set; }
        internal string Stderr { get; set; }
    }

    internal sealed class NasMainForm : Form
    {
        private readonly string _sourceDir;
        private readonly string _workDir;
        private readonly string _mainPs1;
        private readonly string _prepPs1;
        private readonly string _version;
        private readonly int _shareCount;
        private readonly bool _hasRustdesk;
        private readonly bool _hasEquipmentScan;

        private TextBox _tbUser;
        private TextBox _tbPass;
        private Label _lblStatus;
        private Button _btnMount;
        private Button _btnUnmount;
        private Button _btnRefresh;
        private Button _btnRustdesk;
        private Button _btnEquipment;

        internal NasMainForm(
            string sourceDir,
            string workDir,
            string mainPs1,
            string prepPs1,
            string version,
            int shareCount,
            string userHint,
            bool hasRustdesk,
            bool hasEquipmentScan)
        {
            _sourceDir = sourceDir;
            _workDir = workDir;
            _mainPs1 = mainPs1;
            _prepPs1 = prepPs1;
            _version = version ?? "";
            _shareCount = shareCount;
            _hasRustdesk = hasRustdesk;
            _hasEquipmentScan = hasEquipmentScan;

            Text = "JustPlay NAS";
            Font = new Font("Segoe UI", 10F);
            ClientSize = new Size(460, 480);
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
                Text = "K\u1ebft n\u1ed1i NAS JustPlay",
                Font = new Font("Segoe UI", 16F, FontStyle.Bold),
                ForeColor = Color.White,
                AutoSize = true,
                Location = new Point(24, 16),
            };
            header.Controls.Add(lblTitle);

            var sub = _shareCount > 0
                ? string.Format("WebDAV \u2014 {0} \u1ed5 \u0111\u0129a [{1}]", _shareCount, _version)
                : string.Format("Ch\u01b0a c\u00f3 share \u2014 t\u1ea3i l\u1ea1i ZIP [{0}]", _version);
            var lblSub = new Label
            {
                Text = sub,
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
                Size = new Size(412, 268),
                BackColor = Color.White,
                BorderStyle = BorderStyle.FixedSingle,
            };
            Controls.Add(card);

            card.Controls.Add(MakeLabel("T\u00ean \u0111\u0103ng nh\u1eadp Portal", 20, 16));
            _tbUser = new TextBox
            {
                Font = new Font("Segoe UI", 11F),
                Location = new Point(20, 38),
                Size = new Size(372, 28),
                Text = userHint ?? "",
            };
            card.Controls.Add(_tbUser);

            card.Controls.Add(MakeLabel("M\u1eadt kh\u1ea9u Portal", 20, 78));
            _tbPass = new TextBox
            {
                Font = new Font("Segoe UI", 11F),
                Location = new Point(20, 100),
                Size = new Size(372, 28),
                UseSystemPasswordChar = true,
            };
            card.Controls.Add(_tbPass);

            var lblVersion = new Label
            {
                Text = string.Format("Phi\u00ean b\u1ea3n NAS: {0} \u00b7 {1} \u1ed5 \u0111\u0129a WebDAV", _version, _shareCount),
                Font = new Font("Segoe UI", 8.5F),
                ForeColor = Color.FromArgb(100, 116, 139),
                AutoSize = false,
                Size = new Size(372, 18),
                Location = new Point(20, 132),
                TextAlign = ContentAlignment.MiddleLeft,
            };
            card.Controls.Add(lblVersion);

            _btnMount = MakeActionButton("K\u1ebft n\u1ed1i NAS", Color.FromArgb(220, 38, 38), 20, 156, 116);
            _btnUnmount = MakeActionButton("G\u1ee1 mount", Color.FromArgb(71, 85, 105), 148, 156, 116);
            _btnRefresh = MakeActionButton("L\u00e0m m\u1edbi Explorer", Color.FromArgb(71, 85, 105), 276, 156, 116);
            _btnMount.Click += async (s, e) => await RunMountAsync();
            _btnUnmount.Click += async (s, e) => await RunSimpleActionAsync("unmount", "G\u1ee1 mount...");
            _btnRefresh.Click += async (s, e) => await RunSimpleActionAsync("refresh", "L\u00e0m m\u1edbi Explorer...");
            card.Controls.Add(_btnMount);
            card.Controls.Add(_btnUnmount);
            card.Controls.Add(_btnRefresh);

            card.Controls.Add(MakeLabel("C\u00f4ng c\u1ee5 IT", 20, 204));
            _btnRustdesk = MakeActionButton("C\u00e0i RustDesk", Color.FromArgb(37, 99, 235), 20, 226, 180);
            _btnEquipment = MakeActionButton("Th\u00eam C\u1ea5u h\u00ecnh", Color.FromArgb(5, 150, 105), 212, 226, 180);
            _btnRustdesk.Enabled = _hasRustdesk;
            _btnEquipment.Enabled = _hasEquipmentScan;
            _btnRustdesk.Click += async (s, e) => await RunCompanionScriptAsync(
                "JustPlay-RustDesk-Setup.ps1",
                "RustDesk-Setup",
                "\u0110ang c\u00e0i RustDesk...",
                "Ho\u00e0n t\u1ea5t RustDesk. Ki\u1ec3m tra m\u00e1y trong menu RustDesk tr\u00ean Portal.");
            _btnEquipment.Click += async (s, e) => await RunCompanionScriptAsync(
                "JustPlay-Equipment-Scan.ps1",
                "Equipment-Scan",
                "\u0110ang qu\u00e9t c\u1ea5u h\u00ecnh m\u00e1y...",
                "Ho\u00e0n t\u1ea5t. Ki\u1ec3m tra thi\u1ebft b\u1ecb trong Qu\u1ea3n l\u00fd thi\u1ebft b\u1ecb IT tr\u00ean Portal.");
            card.Controls.Add(_btnRustdesk);
            card.Controls.Add(_btnEquipment);

            _lblStatus = new Label
            {
                Text = "S\u1eb5n s\u00e0ng.",
                AutoSize = false,
                Size = new Size(412, 48),
                Location = new Point(24, 398),
                ForeColor = Color.FromArgb(100, 116, 139),
            };
            Controls.Add(_lblStatus);

            AcceptButton = _btnMount;
            Shown += async (s, e) =>
            {
                if (!string.IsNullOrEmpty(_tbUser.Text))
                {
                    _tbPass.Focus();
                }
                else
                {
                    _tbUser.Focus();
                }
                await EnsurePrepAsync();
            };
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
            _btnMount.Enabled = !busy;
            _btnUnmount.Enabled = !busy;
            _btnRefresh.Enabled = !busy;
            _btnRustdesk.Enabled = !busy && _hasRustdesk;
            _btnEquipment.Enabled = !busy && _hasEquipmentScan;
            _lblStatus.Text = status;
            Cursor = busy ? Cursors.WaitCursor : Cursors.Default;
            Application.DoEvents();
        }

        private async Task EnsurePrepAsync()
        {
            SetBusy(true, "\u0110ang chu\u1ea9n b\u1ecb WebClient...");
            try
            {
                var code = await Task.Run(() => RunPrepElevated()).ConfigureAwait(true);
                if (code == 0)
                {
                    _lblStatus.Text = "S\u1eb5n s\u00e0ng.";
                }
                else if (code == 1223)
                {
                    _lblStatus.Text = "Ch\u01b0a c\u1ea5u h\u00ecnh WebClient (UAC b\u1ecb h\u1ee7y). B\u1ea5m K\u1ebft n\u1ed1i NAS v\u00e0 ch\u1ea5p nh\u1eadn UAC.";
                }
                else
                {
                    _lblStatus.Text = "WebClient ch\u01b0a s\u1eb5n s\u00e0ng \u2014 khi K\u1ebft n\u1ed1i NAS h\u00e3y ch\u1ea5p nh\u1eadn UAC (Administrator).";
                }
            }
            catch (Exception ex)
            {
                _lblStatus.Text = ex.Message;
            }
            finally
            {
                SetBusy(false, _lblStatus.Text);
            }
        }

        private int RunPrepElevated()
        {
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = "powershell.exe",
                    Arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" + _prepPs1 + "\"",
                    UseShellExecute = true,
                    Verb = "runas",
                };
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

        private static string FormatConnectSuccessMessage(string stdout)
        {
            var text = (stdout ?? string.Empty).Trim();
            string okLine = null;
            foreach (var line in text.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries))
            {
                var trimmed = line.Trim();
                if (trimmed.StartsWith("OK|", StringComparison.OrdinalIgnoreCase))
                {
                    okLine = trimmed;
                    break;
                }
            }
            if (string.IsNullOrEmpty(okLine))
            {
                return "\u0110\u00e3 k\u1ebft n\u1ed1i NAS th\u00e0nh c\u00f4ng.\nM\u1edf File Explorer \u0111\u1ec3 xem c\u00e1c \u1ed5 \u0111\u0129a.";
            }
            var parts = okLine.Split('|');
            if (parts.Length >= 3 && !string.IsNullOrWhiteSpace(parts[2]))
            {
                var drives = parts[2].Replace("; ", "\n");
                return "\u0110\u00e3 k\u1ebft n\u1ed1i NAS:\n" + drives + "\n\nM\u1edf File Explorer \u0111\u1ec3 duy\u1ec7t file.";
            }
            return "\u0110\u00e3 k\u1ebft n\u1ed1i NAS th\u00e0nh c\u00f4ng.";
        }

        private void TryOpenFirstMappedDrive(string stdout)
        {
            try
            {
                string okLine = null;
                foreach (var line in (stdout ?? string.Empty).Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries))
                {
                    var trimmed = line.Trim();
                    if (trimmed.StartsWith("OK|", StringComparison.OrdinalIgnoreCase))
                    {
                        okLine = trimmed;
                        break;
                    }
                }
                if (string.IsNullOrEmpty(okLine))
                {
                    return;
                }
                var parts = okLine.Split('|');
                if (parts.Length < 3)
                {
                    return;
                }
                var firstMap = parts[2].Split(';')[0].Trim();
                var m = Regex.Match(firstMap, @"^([A-Z]):\s*(.*)$");
                if (!m.Success)
                {
                    return;
                }
                var letter = m.Groups[1].Value;
                var share = m.Groups[2].Value.Trim();
                var user = (_tbUser.Text ?? string.Empty).Trim();
                var path = letter + ":\\";
                if (!string.IsNullOrEmpty(user) &&
                    share.IndexOf("MARKETING", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    path = letter + ":\\" + user;
                }
                Process.Start("explorer.exe", path);
            }
            catch
            {
            }
        }

        private static string FormatConnectFailureMessage(string stdout, string stderr)
        {
            var detail = (stderr ?? string.Empty).Trim();
            if (string.IsNullOrWhiteSpace(detail))
            {
                foreach (var line in (stdout ?? string.Empty).Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries))
                {
                    var trimmed = line.Trim();
                    if (trimmed.StartsWith("OK|", StringComparison.OrdinalIgnoreCase))
                    {
                        continue;
                    }
                    if (trimmed.StartsWith("[JustPlay]", StringComparison.OrdinalIgnoreCase))
                    {
                        continue;
                    }
                    if (!string.IsNullOrWhiteSpace(trimmed))
                    {
                        detail = trimmed;
                        break;
                    }
                }
            }
            if (string.IsNullOrWhiteSpace(detail))
            {
                detail = (stdout ?? string.Empty).Trim();
            }
            if (string.IsNullOrWhiteSpace(detail))
            {
                return "Kh\u00f4ng k\u1ebft n\u1ed1i \u0111\u01b0\u1ee3c NAS.\nTh\u1eed G\u1ee1 mount, ki\u1ec3m tra m\u1eadt kh\u1ea9u Portal, r\u1ed3i K\u1ebft n\u1ed1i l\u1ea1i.";
            }
            if (detail.Length > 1200)
            {
                detail = detail.Substring(0, 1200) + "...";
            }
            return "Kh\u00f4ng k\u1ebft n\u1ed1i \u0111\u01b0\u1ee3c NAS:\n\n" + detail;
        }

        private async Task RunMountAsync()
        {
            var user = _tbUser.Text.Trim();
            if (string.IsNullOrEmpty(user))
            {
                MessageBox.Show(this, "Vui l\u00f2ng nh\u1eadp t\u00ean \u0111\u0103ng nh\u1eadp.", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                _tbUser.Focus();
                return;
            }
            if (string.IsNullOrEmpty(_tbPass.Text))
            {
                MessageBox.Show(this, "Vui l\u00f2ng nh\u1eadp m\u1eadt kh\u1ea9u.", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                _tbPass.Focus();
                return;
            }

            SetBusy(true, "\u0110ang k\u1ebft n\u1ed1i NAS...");
            try
            {
                var result = await RunPs1Async("connect", user, _tbPass.Text).ConfigureAwait(true);
                if (result.ExitCode != 0)
                {
                    var failText = FormatConnectFailureMessage(result.Stdout, result.Stderr);
                    MessageBox.Show(this, failText, Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
                    _lblStatus.Text = "K\u1ebft n\u1ed1i th\u1ea5t b\u1ea1i.";
                    return;
                }
                _lblStatus.Text = "\u0110\u00e3 k\u1ebft n\u1ed1i NAS.";
                var successMsg = FormatConnectSuccessMessage(result.Stdout);
                var portalUser = _tbUser.Text.Trim();
                if (!string.IsNullOrEmpty(portalUser))
                {
                    successMsg += "\n\nThu muc rieng: Z:\\" + portalUser + " (trong o Z: 05_MARKETING)";
                }
                MessageBox.Show(this, successMsg, Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
                TryOpenFirstMappedDrive(result.Stdout);
                await RunPs1Async("refresh", null, null).ConfigureAwait(true);
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

        private async Task RunSimpleActionAsync(string action, string busyText)
        {
            SetBusy(true, busyText);
            try
            {
                var result = await RunPs1Async(action, null, null).ConfigureAwait(true);
                if (result.ExitCode == 0)
                {
                    _lblStatus.Text = action == "unmount"
                        ? "\u0110\u00e3 g\u1ee1 mount NAS."
                        : "\u0110\u00e3 l\u00e0m m\u1edbi Explorer.";
                    MessageBox.Show(this, _lblStatus.Text, Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
                else
                {
                    MessageBox.Show(this, "Thao t\u00e1c th\u1ea5t b\u1ea1i.", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, ex.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally
            {
                SetBusy(false, _lblStatus.Text);
            }
        }

        private async Task RunCompanionScriptAsync(string fileName, string workSubDir, string busyText, string successText)
        {
            var sourcePs1 = Path.Combine(_sourceDir, fileName);
            if (!File.Exists(sourcePs1))
            {
                MessageBox.Show(this, "Thi\u1ebfu file " + fileName + ".\nT\u1ea3i l\u1ea1i ZIP t\u1eeb Portal.", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
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
                        ? "Cần chấp nhận UAC (quyền Administrator).\n\n• Bấm Có khi Windows hỏi\n• Nếu đã bấm Không: chạy lại «Cài RustDesk»\n• Hoặc chuột phải JustPlay-RustDesk-Setup.cmd → Run as administrator"
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
                // UAC cancelled
                if (ex.NativeErrorCode == 1223)
                {
                    return 1223;
                }
                throw;
            }
        }

        private Task<PsRunResult> RunPs1Async(string action, string user, string password)
        {
            return Task.Run(() =>
            {
                var args = "-NoProfile -ExecutionPolicy Bypass -File \"" + _mainPs1 + "\" " + action;
                if (action == "connect")
                {
                    args += " \"" + user.Replace("\"", "`\"") + "\"";
                }
                var psi = new ProcessStartInfo
                {
                    FileName = "powershell.exe",
                    Arguments = args,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                };
                if (action == "connect" && password != null)
                {
                    psi.EnvironmentVariables["JUSTPLAY_NAS_CLI_PASSWORD"] = password;
                }
                using (var proc = Process.Start(psi))
                {
                    if (proc == null)
                    {
                        return new PsRunResult { ExitCode = 1, Stdout = "", Stderr = "Khong khoi chay PowerShell." };
                    }
                    var stdout = proc.StandardOutput.ReadToEnd();
                    var stderr = proc.StandardError.ReadToEnd();
                    proc.WaitForExit();
                    return new PsRunResult
                    {
                        ExitCode = proc.ExitCode,
                        Stdout = stdout ?? "",
                        Stderr = stderr ?? "",
                    };
                }
            });
        }
    }

    internal static class NativeMethods
    {
        [System.Runtime.InteropServices.DllImport("gdi32.dll")]
        internal static extern IntPtr CreateRoundRectRgn(int x1, int y1, int x2, int y2, int cx, int cy);
    }

    internal static class Program
    {
        private static string WorkDir
        {
            get
            {
                return Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "JustPlay",
                    "NAS-Setup");
            }
        }

        [STAThread]
        private static int Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            try
            {
                var sourceDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\', '/');
                UnblockDirectory(sourceDir);
                SyncBundle(sourceDir, WorkDir);
                UnblockDirectory(WorkDir);

                var mainPs1 = Path.Combine(WorkDir, "JustPlay-NAS-RaiDrive-Setup.ps1");
                var prepPs1 = Path.Combine(WorkDir, "Prepare-JustPlay-WebClient.ps1");
                if (!File.Exists(mainPs1) || !File.Exists(prepPs1))
                {
                    MessageBox.Show(
                        "Thi\u1ebfu file c\u00e0i \u0111\u1eb7t.\nT\u1ea3i l\u1ea1i ZIP t\u1eeb Portal v\u00e0 gi\u1ea3i n\u00e9n \u0111\u1ee7 file.",
                        "JustPlay NAS",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                    return 1;
                }

                string userHint;
                int shareCount;
                string version;
                bool hasRustdesk;
                bool hasEquipmentScan;
                ReadBundleMeta(WorkDir, out userHint, out shareCount, out version, out hasRustdesk, out hasEquipmentScan);

                Application.Run(new NasMainForm(
                    sourceDir,
                    WorkDir,
                    mainPs1,
                    prepPs1,
                    version,
                    shareCount,
                    userHint,
                    hasRustdesk,
                    hasEquipmentScan));
                return 0;
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message, "JustPlay NAS", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }

        private static void ReadBundleMeta(
            string workDir,
            out string userHint,
            out int shareCount,
            out string version,
            out bool hasRustdesk,
            out bool hasEquipmentScan)
        {
            userHint = "";
            shareCount = 0;
            version = "";
            hasRustdesk = File.Exists(Path.Combine(workDir, "JustPlay-RustDesk-Setup.ps1"));
            hasEquipmentScan = File.Exists(Path.Combine(workDir, "JustPlay-Equipment-Scan.ps1"));
            var cfgPath = Path.Combine(workDir, "JustPlay-NAS-Config.json");
            var ps1Path = Path.Combine(workDir, "JustPlay-NAS-RaiDrive-Setup.ps1");
            if (File.Exists(cfgPath))
            {
                var json = File.ReadAllText(cfgPath);
                var um = Regex.Match(json, "\"portal_username\"\\s*:\\s*\"([^\"]*)\"");
                if (um.Success)
                {
                    userHint = um.Groups[1].Value;
                }
                var sm = Regex.Matches(json, "\"shares\"\\s*:\\s*\\[([\\s\\S]*?)\\]");
                if (sm.Count > 0)
                {
                    shareCount = Regex.Matches(sm[0].Groups[1].Value, "\"[^\"]+\"").Count;
                }
                var rd = Regex.Match(json, "\"has_rustdesk\"\\s*:\\s*(true|false)");
                if (rd.Success)
                {
                    hasRustdesk = rd.Groups[1].Value == "true";
                }
                var eq = Regex.Match(json, "\"has_equipment_scan\"\\s*:\\s*(true|false)");
                if (eq.Success)
                {
                    hasEquipmentScan = eq.Groups[1].Value == "true";
                }
            }
            if (File.Exists(ps1Path))
            {
                var vm = Regex.Match(File.ReadAllText(ps1Path), @"\$NasScriptVersion\s*=\s*'([^']+)'");
                if (vm.Success)
                {
                    version = vm.Groups[1].Value;
                }
            }
        }

        private static void SyncBundle(string sourceDir, string workDir)
        {
            Directory.CreateDirectory(workDir);
            var names = new[]
            {
                "JustPlay-NAS-RaiDrive-Setup.ps1",
                "Prepare-JustPlay-WebClient.ps1",
                "JustPlay-NAS-Config.json",
                "JustPlay-RustDesk-Setup.ps1",
                "JustPlay-Equipment-Scan.ps1",
            };
            foreach (var name in names)
            {
                var src = Path.Combine(sourceDir, name);
                if (!File.Exists(src))
                {
                    if (name == "JustPlay-NAS-Config.json"
                        || name == "JustPlay-RustDesk-Setup.ps1"
                        || name == "JustPlay-Equipment-Scan.ps1")
                    {
                        continue;
                    }
                    throw new FileNotFoundException("Thieu file " + name);
                }
                File.Copy(src, Path.Combine(workDir, name), true);
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
