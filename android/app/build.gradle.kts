plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "dev.opencaption.opencaption"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = "28.2.13676358"

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "dev.opencaption.opencaption"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        // ggml's Vulkan backend links Vulkan 1.1 entry points that Android
        // exposes from API 28. The target devices (Snapdragon 8 Elite) are
        // substantially newer, so prefer a real GPU path over CPU-only API 26.
        minSdk = 28
        ndk { abiFilters += "arm64-v8a" }
        externalNativeBuild {
            cmake {
                cppFlags += "-std=c++17"
                abiFilters += "arm64-v8a"
            }
        }
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        buildConfigField(
            "boolean",
            "DIAGNOSTICS_ENABLED",
            (findProperty("diagnostics")?.toString()?.toBoolean() ?: false).toString(),
        )
    }

    signingConfigs {
        getByName("debug") {
            // Flutter's wrapper isolates XDG_CONFIG_HOME, which otherwise
            // makes AGP silently generate a second debug key. Pin one stable
            // key so test APK updates preserve the app-private model files.
            storeFile = file("${System.getProperty("user.home")}/.android/debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
    }

    flavorDimensions += "engine"
    productFlavors {
        create("cascade") {
            dimension = "engine"
            applicationIdSuffix = ".cascade"
            manifestPlaceholders["appLabel"] = "OpenCaption · 级联"
        }
        create("gemmaE2E") {
            dimension = "engine"
            applicationIdSuffix = ".gemma"
            manifestPlaceholders["appLabel"] = "OpenCaption · Gemma E2E"
        }
        create("qwenE2E") {
            dimension = "engine"
            applicationIdSuffix = ".qwenomni"
            manifestPlaceholders["appLabel"] = "OpenCaption · Qwen Omni E2E"
            externalNativeBuild.cmake.arguments += "-DOPENCAPTION_QWEN_E2E=ON"
        }
    }

    buildTypes {
        release {
            // LiteRT-LM resolves part of its engine through Kotlin/Java metadata
            // and native bindings. Flutter enables R8 for release builds by
            // default; shrinking those classes makes the Gemma app crash at
            // startup/inference even though the debug APK works. Keep release
            // unshrunk until a tested keep-rule set is available.
            isMinifyEnabled = false
            isShrinkResources = false
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }
}

dependencies {
    implementation("com.google.mlkit:translate:17.0.3")
    add("gemmaE2EImplementation", "com.google.ai.edge.litertlm:litertlm-android:0.17.0")
    testImplementation("junit:junit:4.13.2")
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
