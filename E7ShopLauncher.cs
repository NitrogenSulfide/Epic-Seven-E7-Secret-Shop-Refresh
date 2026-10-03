using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class E7ShopLauncher
{
    [STAThread]
    private static int Main(string[] args)
    {
        string directory = AppDomain.CurrentDomain.BaseDirectory;
        string script = Path.Combine(directory, "e7_shop_refresh_gui.py");
        string launcher = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "pyw.exe");
        bool verify = args.Length == 1 && args[0] == "--verify";
        try
        {
            if (!File.Exists(script) || !File.Exists(Path.Combine(directory, "e7_process.py")))
                throw new FileNotFoundException("Keep this launcher beside e7_shop_refresh_gui.py and e7_process.py.");
            if (!File.Exists(launcher))
            {
                launcher = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python", "Launcher", "pyw.exe");
                if (!File.Exists(launcher)) throw new FileNotFoundException("Python's Windows launcher (pyw.exe) is missing.");
            }
            if (verify) return 0;
            ProcessStartInfo start = new ProcessStartInfo(launcher, "-3 \"" + script + "\"");
            start.WorkingDirectory = directory;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            Process.Start(start);
            return 0;
        }
        catch (Exception error)
        {
            if (!verify) MessageBox.Show(error.Message, "E7 Secret Shop Refresh", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
