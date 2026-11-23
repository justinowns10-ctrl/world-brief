package com.worldbrief.app.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat
import com.worldbrief.app.data.ThemeMode
import com.worldbrief.app.data.model.StoryStatus

// A newspaper palette: paper and ink, one restrained blue accent. No dynamic
// colour, so the app looks the same on every phone.
private val LightColors = lightColorScheme(
    primary = Color(0xFF1F4E79),
    onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFD6E4F2),
    onPrimaryContainer = Color(0xFF0E2A44),
    secondary = Color(0xFF5B6470),
    onSecondary = Color(0xFFFFFFFF),
    secondaryContainer = Color(0xFFE6E3DA),
    onSecondaryContainer = Color(0xFF23272D),
    background = Color(0xFFFAF8F3),
    onBackground = Color(0xFF1B1B1A),
    surface = Color(0xFFFAF8F3),
    onSurface = Color(0xFF1B1B1A),
    surfaceVariant = Color(0xFFEDEAE1),
    onSurfaceVariant = Color(0xFF55575A),
    surfaceContainer = Color(0xFFF1EEE6),
    surfaceContainerHigh = Color(0xFFEBE8DF),
    outline = Color(0xFF8A8C8F),
    outlineVariant = Color(0xFFD9D5CA),
    error = Color(0xFFA3271F),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF9CC4E4),
    onPrimary = Color(0xFF0B2A44),
    primaryContainer = Color(0xFF1D3F5E),
    onPrimaryContainer = Color(0xFFD6E4F2),
    secondary = Color(0xFFB7BEC8),
    onSecondary = Color(0xFF22272E),
    secondaryContainer = Color(0xFF2B3037),
    onSecondaryContainer = Color(0xFFE0E3E8),
    background = Color(0xFF0F1113),
    onBackground = Color(0xFFE8E5DE),
    surface = Color(0xFF0F1113),
    onSurface = Color(0xFFE8E5DE),
    surfaceVariant = Color(0xFF1E2226),
    onSurfaceVariant = Color(0xFFAEB1B5),
    surfaceContainer = Color(0xFF171A1D),
    surfaceContainerHigh = Color(0xFF1E2226),
    outline = Color(0xFF7C8085),
    outlineVariant = Color(0xFF2E3338),
    error = Color(0xFFFFB4AB),
)

private val Base = Typography()

/** Serif for headlines, the platform sans for everything else. */
private val AppTypography = Typography(
    displaySmall = Base.displaySmall.copy(fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold),
    headlineLarge = Base.headlineLarge.copy(fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold),
    headlineMedium = Base.headlineMedium.copy(fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold),
    headlineSmall = Base.headlineSmall.copy(fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold),
    titleLarge = Base.titleLarge.copy(fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold),
    titleMedium = Base.titleMedium.copy(fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold, fontSize = 18.sp, lineHeight = 24.sp),
    bodyLarge = Base.bodyLarge.copy(lineHeight = 26.sp),
    bodyMedium = Base.bodyMedium.copy(lineHeight = 22.sp),
    labelSmall = Base.labelSmall.copy(letterSpacing = 1.2.sp, fontWeight = FontWeight.SemiBold),
)

val LocalIsDark = staticCompositionLocalOf { false }

@Composable
fun WorldBriefTheme(themeMode: ThemeMode, textScale: Float, content: @Composable () -> Unit) {
    val dark = when (themeMode) {
        ThemeMode.SYSTEM -> isSystemInDarkTheme()
        ThemeMode.LIGHT -> false
        ThemeMode.DARK -> true
    }
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as? Activity)?.window
            if (window != null) {
                val controller = WindowCompat.getInsetsController(window, view)
                controller.isAppearanceLightStatusBars = !dark
                controller.isAppearanceLightNavigationBars = !dark
            }
        }
    }
    // The in-app text size multiplies the system font scale.
    val density = LocalDensity.current
    val scaled = Density(density.density, density.fontScale * textScale)
    CompositionLocalProvider(LocalDensity provides scaled, LocalIsDark provides dark) {
        MaterialTheme(
            colorScheme = if (dark) DarkColors else LightColors,
            typography = AppTypography,
            content = content,
        )
    }
}

@Composable
fun statusColor(status: StoryStatus): Color {
    val dark = LocalIsDark.current
    return when (status) {
        StoryStatus.VERIFIED -> if (dark) Color(0xFF86CDA4) else Color(0xFF1E6B45)
        StoryStatus.PRELIMINARY -> if (dark) Color(0xFFE6C06A) else Color(0xFF8A5A00)
        StoryStatus.DISPUTED -> if (dark) Color(0xFFFFA59A) else Color(0xFFA3271F)
    }
}

@Composable
fun cautionColor(): Color = if (LocalIsDark.current) Color(0xFFE6C06A) else Color(0xFF8A5A00)
