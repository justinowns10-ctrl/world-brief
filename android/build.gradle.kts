// Kotlin compilation is built into the Android Gradle plugin (AGP 9+), so the
// separate kotlin-android plugin is not applied.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.ksp) apply false
}
