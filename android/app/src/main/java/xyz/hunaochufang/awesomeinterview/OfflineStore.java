package xyz.hunaochufang.awesomeinterview;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;

import org.json.JSONObject;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Arrays;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** One encrypted, owner-scoped read-only snapshot on this device. */
final class OfflineStore {
    private static final String KEY_ALIAS = "awesome_interview_snapshot_v1";
    private static final String FILE_NAME = "private_snapshot.bin";
    private static final String PREFS = "offline_state";

    private OfflineStore() { }

    static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static File file(Context context) {
        return new File(context.getFilesDir(), FILE_NAME);
    }

    private static SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(KEY_ALIAS)) {
            return (SecretKey) store.getKey(KEY_ALIAS, null);
        }
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build());
        return generator.generateKey();
    }

    static void save(Context context, JSONObject snapshot) throws Exception {
        String userId = snapshot.getString("user_id");
        String previous = prefs(context).getString("user_id", null);
        if (previous != null && !previous.equals(userId)) clear(context);
        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key(), new GCMParameterSpec(128, nonce));
        byte[] encrypted = cipher.doFinal(snapshot.toString().getBytes(StandardCharsets.UTF_8));
        byte[] output = Arrays.copyOf(nonce, nonce.length + encrypted.length);
        System.arraycopy(encrypted, 0, output, nonce.length, encrypted.length);
        File temporary = new File(context.getFilesDir(), FILE_NAME + ".tmp");
        Files.write(temporary.toPath(), output);
        Files.move(temporary.toPath(), file(context).toPath(), StandardCopyOption.REPLACE_EXISTING);
        prefs(context).edit().putString("user_id", userId)
                .putString("synced_at", snapshot.getString("server_time")).apply();
    }

    static JSONObject load(Context context) throws Exception {
        byte[] input = Files.readAllBytes(file(context).toPath());
        if (input.length < 29) throw new IllegalStateException("缓存不完整");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Arrays.copyOf(input, 12)));
        JSONObject snapshot = new JSONObject(new String(
                cipher.doFinal(Arrays.copyOfRange(input, 12, input.length)), StandardCharsets.UTF_8));
        if (!snapshot.getString("user_id").equals(prefs(context).getString("user_id", null))) {
            throw new IllegalStateException("账号与缓存不匹配");
        }
        return snapshot;
    }

    static void clear(Context context) {
        File cached = file(context);
        if (cached.exists() && !cached.delete()) throw new IllegalStateException("无法清除本地缓存");
        prefs(context).edit().clear().apply();
    }
}
