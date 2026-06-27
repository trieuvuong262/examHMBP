using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace JustPlay.NasLauncher
{
    internal sealed class NasMainForm : Form
    {
        private readonly string _workDir;
        private readonly string _mainPs1;
        private readonly string _prepPs1;
        private readonly string _version;
        private readonly int _shareCount;

        private TextBox _tbUser;
        private TextBox _tbPass;
        private Label _lblStatus;
        private Button _btnMount;
        private Button _btnUnmount;
        private Button _btnRefresh;

        internal NasMainForm(string workDir, string mainPs1, string prepPs1, string version, int shareCount, string userHint)
        {
            _workDir = workDir;
            _mainPs1 = mainPs1;
            _prepPs1 = prepPs1;
            _version = version ?? "";
            _shareCount = shareCount;

            Text = "JustPlay NAS";
            Font = new Font("Segoe UI", 10F);
            ClientSize = new Size(460, 400);
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
                Size = new Size(412, 200),
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

            _btnMount = MakeActionButton("K\u1ebft n\u1ed1i NAS", Color.FromArgb(220, 38, 38), 20, 148);
            _btnUnmount = MakeActionButton("G\u1ee1 mount", Color.FromArgb(71, 85, 105), 148, 148);
            _btnRefresh = MakeActionButton("L\u00e0m m\u1edbi Explorer", Color.FromArgb(71, 85, 105), 276, 148);
            _btnMount.Click += async (s, e) => await RunMountAsync();
            _btnUnmount.Click += async (s, e) => await RunSimpleActionAsync("unmount", "G\u1ee1 mount...");
            _btnRefresh.Click += async (s, e) => await RunSimpleActionAsync("refresh", "L\u00e0m m\u1edbi Explorer...");
            card.Controls.Add(_btnMount);
            card.Controls.Add(_btnUnmount);
            card.Controls.Add(_btnRefresh);

            _lblStatus = new Label
            {
                Text = "S\u1eb5n s\u00e0ng.",
                AutoSize = false,
                Size = new Size(412, 40),
                Location = new Point(24, 318),
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

        private Button MakeActionButton(string text, Color bg, int x, int y)
        {
            var btn = new Button
            {
                Text = text,
                FlatStyle = FlatStyle.Flat,
                BackColor = bg,
                ForeColor = Color.White,
                Font = new Font("Segoe UI", 9F, FontStyle.Bold),
                Size = new Size(116, 36),
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
            _lblStatus.Text = status;
            Cursor = busy ? Cursors.WaitCursor : Cursors.Default;
            Application.DoEvents();
        }

        private async Task EnsurePrepAsync()
        {
            SetBusy(true, "\u0110ang chu\u1ea9n b\u1ecb WebClient...");
            try
            {
                var code = await RunPs1Async("prep", null, null).ConfigureAwait(true);
                if (code != 0)
                {
                    _lblStatus.Text = "WebClient: ch\u1ea5p nh\u1eadn UAC n\u1ebfu \u0111\u01b0\u1ee3c h\u1ecfi, r\u1ed3i th\u1eed K\u1ebft n\u1ed1i.";
                }
                else
                {
                    _lblStatus.Text = "S\u1eb5n s\u00e0ng.";
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
                var code = await RunPs1Async("connect", user, _tbPass.Text).ConfigureAwait(true);
                if (code != 0)
                {
                    MessageBox.Show(this, "Kh\u00f4ng k\u1ebft n\u1ed1i \u0111\u01b0\u1ee3c NAS.\nXem chi ti\u1ebft trong c\u1eeda s\u1ed5 PowerShell (n\u1ebfu c\u00f3).", Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
                    _lblStatus.Text = "K\u1ebft n\u1ed1i th\u1ea5t b\u1ea1i.";
                    return;
                }
                _lblStatus.Text = "\u0110\u00e3 k\u1ebft n\u1ed1i NAS.";
                MessageBox.Show(this, "\u0110\u00e3 k\u1ebft n\u1ed1i NAS th\u00e0nh c\u00f4ng.\nM\u1edf File Explorer \u0111\u1ec3 xem Z, Y, X, W.", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
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
                var code = await RunPs1Async(action, null, null).ConfigureAwait(true);
                if (code == 0)
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

        private Task<int> RunPs1Async(string action, string user, string password)
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
                        return 1;
                    }
                    var err = proc.StandardError.ReadToEnd();
                    proc.WaitForExit();
                    if (proc.ExitCode != 0 && !string.IsNullOrWhiteSpace(err))
                    {
                        throw new InvalidOperationException(err.Trim());
                    }
                    return proc.ExitCode;
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
                ReadBundleMeta(WorkDir, out userHint, out shareCount, out version);

                Application.Run(new NasMainForm(WorkDir, mainPs1, prepPs1, version, shareCount, userHint));
                return 0;
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message, "JustPlay NAS", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }

        private static void ReadBundleMeta(string workDir, out string userHint, out int shareCount, out string version)
        {
            userHint = "";
            shareCount = 0;
            version = "";
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
                shareCount = Regex.Matches(json, "\"shares\"\\s*:\\s*\\[([^\\]]*)\\]").Count > 0
                    ? Regex.Matches(json, "\"([^\"]+)\"\\s*,?\\s*(?=\\]|$)").Count
                    : 0;
                var sm = Regex.Matches(json, "\"shares\"\\s*:\\s*\\[([\\s\\S]*?)\\]");
                if (sm.Count > 0)
                {
                    shareCount = Regex.Matches(sm[0].Groups[1].Value, "\"[^\"]+\"").Count;
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
            };
            foreach (var name in names)
            {
                var src = Path.Combine(sourceDir, name);
                if (!File.Exists(src))
                {
                    if (name == "JustPlay-NAS-Config.json")
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
