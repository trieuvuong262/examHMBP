using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

namespace JustPlay.NasLauncher
{
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
            try
            {
                var sourceDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\', '/');
                UnblockDirectory(sourceDir);
                SyncBundle(sourceDir, WorkDir);
                UnblockDirectory(WorkDir);

                var prep = Path.Combine(WorkDir, "Prepare-JustPlay-WebClient.ps1");
                var main = Path.Combine(WorkDir, "JustPlay-NAS-RaiDrive-Setup.ps1");

                if (!File.Exists(prep) || !File.Exists(main))
                {
                    MessageBox.Show(
                        "Thieu file trong bo cai.\nGiai nen day du ZIP (ps1 + json) cung thu muc voi file .exe.",
                        "JustPlay NAS",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                    return 1;
                }

                var prepStart = new ProcessStartInfo
                {
                    FileName = "powershell.exe",
                    Arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" + prep + "\"",
                    UseShellExecute = true,
                    WindowStyle = ProcessWindowStyle.Hidden,
                };
                using (var prepProc = Process.Start(prepStart))
                {
                    if (prepProc == null)
                    {
                        MessageBox.Show(
                            "Khong khoi dong duoc PowerShell.",
                            "JustPlay NAS",
                            MessageBoxButtons.OK,
                            MessageBoxIcon.Error);
                        return 1;
                    }
                    prepProc.WaitForExit();
                    if (prepProc.ExitCode != 0)
                    {
                        MessageBox.Show(
                            "Khong cau hinh duoc WebClient.\nChap nhan UAC khi duoc hoi va chay lai.",
                            "JustPlay NAS",
                            MessageBoxButtons.OK,
                            MessageBoxIcon.Warning);
                        return prepProc.ExitCode;
                    }
                }

                var guiArgs = "powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File \"" + main + "\"";
                Process.Start("explorer.exe", guiArgs);
                return 0;
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    ex.Message,
                    "JustPlay NAS",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return 1;
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
                    throw new FileNotFoundException("Thieu file " + name + " trong thu muc cai dat.");
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
            try
            {
                var escaped = dir.Replace("'", "''");
                var psi = new ProcessStartInfo
                {
                    FileName = "powershell.exe",
                    Arguments = "-NoProfile -Command \"Get-ChildItem -LiteralPath '" + escaped +
                                "' -File | Unblock-File -ErrorAction SilentlyContinue\"",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden,
                };
                using (var p = Process.Start(psi))
                {
                    if (p != null)
                    {
                        p.WaitForExit(8000);
                    }
                }
            }
            catch
            {
            }
        }
    }
}
