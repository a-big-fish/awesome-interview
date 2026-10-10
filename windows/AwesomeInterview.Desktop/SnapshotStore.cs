using System.Security.Cryptography;
using System.IO;
using System.Text;
using System.Text.Json;

namespace AwesomeInterview.Desktop;

internal sealed class SnapshotStore
{
    private static readonly byte[] Entropy = Encoding.UTF8.GetBytes("AwesomeInterview.Windows.1.0-W");
    private readonly string _folder = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AwesomeInterview");

    private string PathName => Path.Combine(_folder, "personal-snapshot.bin");
    private string FiredPath => Path.Combine(_folder, "fired-reminders.bin");
    public string DirectoryPath => _folder;

    public JsonDocument? Read()
    {
        if (!File.Exists(PathName)) return null;
        try
        {
            var encrypted = File.ReadAllBytes(PathName);
            var plain = ProtectedData.Unprotect(encrypted, Entropy, DataProtectionScope.CurrentUser);
            var document = JsonDocument.Parse(plain);
            if (document.RootElement.GetProperty("schema_version").GetInt32() != 1)
            {
                document.Dispose();
                return null;
            }
            return document;
        }
        catch (Exception error) when (error is CryptographicException or IOException or JsonException or KeyNotFoundException)
        {
            return null;
        }
    }

    public string? OwnerId()
    {
        using var document = Read();
        return document?.RootElement.GetProperty("user_id").GetString();
    }

    public void Save(JsonDocument document)
    {
        var root = document.RootElement;
        if (root.GetProperty("schema_version").GetInt32() != 1 ||
            string.IsNullOrWhiteSpace(root.GetProperty("user_id").GetString()))
            throw new InvalidDataException("快照格式或账号无效");
        Directory.CreateDirectory(_folder);
        var plain = Encoding.UTF8.GetBytes(root.GetRawText());
        var encrypted = ProtectedData.Protect(plain, Entropy, DataProtectionScope.CurrentUser);
        var temporary = PathName + ".tmp";
        File.WriteAllBytes(temporary, encrypted);
        File.Move(temporary, PathName, true);
    }

    public void Clear()
    {
        if (File.Exists(PathName)) File.Delete(PathName);
        if (File.Exists(FiredPath)) File.Delete(FiredPath);
    }

    public HashSet<string> ReadFiredKeys()
    {
        try
        {
            if (!File.Exists(FiredPath)) return new HashSet<string>();
            var plain = ProtectedData.Unprotect(File.ReadAllBytes(FiredPath), Entropy, DataProtectionScope.CurrentUser);
            return JsonSerializer.Deserialize<HashSet<string>>(plain) ?? new HashSet<string>();
        }
        catch (Exception error) when (error is CryptographicException or IOException or JsonException)
        {
            return new HashSet<string>();
        }
    }

    public void SaveFiredKeys(HashSet<string> keys)
    {
        Directory.CreateDirectory(_folder);
        var encrypted = ProtectedData.Protect(JsonSerializer.SerializeToUtf8Bytes(keys), Entropy,
            DataProtectionScope.CurrentUser);
        var temporary = FiredPath + ".tmp";
        File.WriteAllBytes(temporary, encrypted);
        File.Move(temporary, FiredPath, true);
    }
}
