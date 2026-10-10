import java.net.URI

plugins {
    id("com.android.application")
}

android {
    namespace = "xyz.hunaochufang.awesomeinterview"
    compileSdk = 36

    buildFeatures { buildConfig = true }

    defaultConfig {
        applicationId = "xyz.hunaochufang.awesomeinterview"
        minSdk = 26
        targetSdk = 36
        versionCode = 2
        versionName = "1.0.0-alpha2"
        val serverOrigin = providers.gradleProperty("serverOrigin")
            .getOrElse("https://example.invalid").trimEnd('/')
        val originUri = URI(serverOrigin)
        require(originUri.scheme == "https" && originUri.host != null &&
            originUri.rawPath.isNullOrEmpty() && originUri.rawQuery == null &&
            originUri.rawFragment == null && '"' !in serverOrigin) {
            "serverOrigin must be an HTTPS origin"
        }
        buildConfigField("String", "SERVER_ORIGIN", "\"$serverOrigin\"")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
