package com.worldbrief.app.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import com.worldbrief.app.AppContainer

val LocalAppContainer = staticCompositionLocalOf<AppContainer> {
    error("AppContainer was not provided")
}

class ContainerFactory(private val producer: () -> ViewModel) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T = producer() as T
}

/**
 * Creates a ViewModel from the app container. [key] must differ for ViewModels
 * of the same class that show different things (for example two stories).
 */
@Composable
inline fun <reified VM : ViewModel> appViewModel(
    key: String? = null,
    noinline create: (AppContainer) -> VM,
): VM {
    val container = LocalAppContainer.current
    return viewModel<VM>(key = key, factory = ContainerFactory { create(container) })
}
