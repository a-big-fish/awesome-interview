using System.Windows;

namespace AwesomeInterview.Desktop;

public partial class App : System.Windows.Application
{
    private void OnStartup(object sender, StartupEventArgs args)
    {
        var window = new MainWindow();
        MainWindow = window;
        window.Show();
    }
}
