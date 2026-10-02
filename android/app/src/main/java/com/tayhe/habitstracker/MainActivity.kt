package com.tayhe.habitstracker

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.view.WindowManager
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.google.android.material.switchmaterial.SwitchMaterial

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var swipeRefreshLayout: SwipeRefreshLayout
    private lateinit var progressBar: ProgressBar
    private lateinit var errorContainer: View
    private lateinit var btnRetry: Button
    private lateinit var btnSettings: Button

    private lateinit var prefs: SharedPreferences
    private var lastBackPressTime: Long = 0
    private var cornerTapCount = 0
    private var lastCornerTapTime: Long = 0

    companion object {
        private const val PREFS_NAME = "habits_tracker_prefs"
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_KEEP_SCREEN_ON = "keep_screen_on"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

        initViews()
        setupImmersiveMode()
        applyKeepScreenOn(prefs.getBoolean(KEY_KEEP_SCREEN_ON, true))
        setupWebView()
        setupBackPressHandler()
        setupSecretSettingsTrigger()

        loadCurrentUrl()
    }

    private fun initViews() {
        webView = findViewById(R.id.webView)
        swipeRefreshLayout = findViewById(R.id.swipeRefreshLayout)
        progressBar = findViewById(R.id.progressBar)
        errorContainer = findViewById(R.id.errorContainer)
        btnRetry = findViewById(R.id.btnRetry)
        btnSettings = findViewById(R.id.btnSettings)

        btnRetry.setOnClickListener {
            errorContainer.visibility = View.GONE
            webView.visibility = View.VISIBLE
            webView.reload()
        }

        btnSettings.setOnClickListener {
            showSettingsDialog()
        }

        swipeRefreshLayout.setColorSchemeResources(R.color.primary)
        swipeRefreshLayout.setOnRefreshListener {
            webView.reload()
        }
    }

    private fun setupImmersiveMode() {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val controller = WindowInsetsControllerCompat(window, window.decorView)
        controller.hide(WindowInsetsCompat.Type.systemBars())
        controller.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
    }

    private fun applyKeepScreenOn(enabled: Boolean) {
        if (enabled) {
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        } else {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        val settings: WebSettings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.useWideViewPort = true
        settings.loadWithOverviewMode = true
        settings.setSupportZoom(false)
        settings.builtInZoomControls = false
        settings.displayZoomControls = false
        settings.cacheMode = WebSettings.LOAD_DEFAULT
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE

        val cookieManager = CookieManager.getInstance()
        cookieManager.setAcceptCookie(true)
        cookieManager.setAcceptThirdPartyCookies(webView, true)

        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                super.onPageStarted(view, url, favicon)
                progressBar.visibility = View.VISIBLE
                errorContainer.visibility = View.GONE
                webView.visibility = View.VISIBLE
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                progressBar.visibility = View.GONE
                swipeRefreshLayout.isRefreshing = false
                cookieManager.flush()
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    webView.visibility = View.GONE
                    errorContainer.visibility = View.VISIBLE
                    swipeRefreshLayout.isRefreshing = false
                    progressBar.visibility = View.GONE
                }
            }

            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val url = request?.url?.toString() ?: return false
                if (url.startsWith("http://") || url.startsWith("https://")) {
                    return false
                }
                return try {
                    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
                    startActivity(intent)
                    true
                } catch (e: Exception) {
                    true
                }
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                super.onProgressChanged(view, newProgress)
                progressBar.progress = newProgress
                if (newProgress == 100) {
                    progressBar.visibility = View.GONE
                }
            }
        }
    }

    private fun setupBackPressHandler() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) {
                    webView.goBack()
                } else {
                    val now = System.currentTimeMillis()
                    if (now - lastBackPressTime < 2000) {
                        finish()
                    } else {
                        lastBackPressTime = now
                        Toast.makeText(this@MainActivity, R.string.exit_prompt, Toast.LENGTH_SHORT).show()
                    }
                }
            }
        })
    }

    /**
     * 针对平板设计的隐形设置入口：
     * 连续快速点击屏幕右上角 3 次，弹出服务器设置窗口（防小朋友误操作，家长方便调出）。
     */
    private fun setupSecretSettingsTrigger() {
        val root = findViewById<View>(R.id.rootContainer)
        root.setOnTouchListener { _, event ->
            if (event.action == android.view.MotionEvent.ACTION_DOWN) {
                val screenWidth = resources.displayMetrics.widthPixels
                if (event.rawX > screenWidth - 200 && event.rawY < 200) {
                    val now = System.currentTimeMillis()
                    if (now - lastCornerTapTime < 600) {
                        cornerTapCount++
                        if (cornerTapCount >= 3) {
                            cornerTapCount = 0
                            showSettingsDialog()
                        }
                    } else {
                        cornerTapCount = 1
                    }
                    lastCornerTapTime = now
                }
            }
            false
        }
    }

    private fun getCurrentUrl(): String {
        val defaultUrl = getString(R.string.default_url)
        return prefs.getString(KEY_SERVER_URL, defaultUrl) ?: defaultUrl
    }

    private fun loadCurrentUrl() {
        val url = getCurrentUrl()
        webView.loadUrl(url)
    }

    private fun showSettingsDialog() {
        val context = this
        val dialogView = layoutInflater.inflate(android.R.layout.select_dialog_item, null) // fallback base
        val container = android.widget.LinearLayout(context).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(50, 40, 50, 20)
        }

        val urlInput = EditText(context).apply {
            setText(getCurrentUrl())
            hint = getString(R.string.settings_hint)
            inputType = android.text.InputType.TYPE_TEXT_VARIATION_URI
        }
        container.addView(urlInput)

        val keepScreenOnSwitch = SwitchMaterial(context).apply {
            text = getString(R.string.keep_screen_on_title)
            isChecked = prefs.getBoolean(KEY_KEEP_SCREEN_ON, true)
            setPadding(0, 30, 0, 0)
        }
        container.addView(keepScreenOnSwitch)

        AlertDialog.Builder(context)
            .setTitle(R.string.settings_title)
            .setView(container)
            .setPositiveButton(R.string.save) { _, _ ->
                var newUrl = urlInput.text.toString().trim()
                if (!newUrl.startsWith("http://") && !newUrl.startsWith("https://")) {
                    newUrl = "https://$newUrl"
                }
                val keepOn = keepScreenOnSwitch.isChecked

                prefs.edit()
                    .putString(KEY_SERVER_URL, newUrl)
                    .putBoolean(KEY_KEEP_SCREEN_ON, keepOn)
                    .apply()

                applyKeepScreenOn(keepOn)
                webView.loadUrl(newUrl)
                Toast.makeText(context, "已更新设置并重新加载", Toast.LENGTH_SHORT).show()
            }
            .setNeutralButton(R.string.reset_default) { _, _ ->
                val defaultUrl = getString(R.string.default_url)
                prefs.edit()
                    .putString(KEY_SERVER_URL, defaultUrl)
                    .putBoolean(KEY_KEEP_SCREEN_ON, true)
                    .apply()

                applyKeepScreenOn(true)
                webView.loadUrl(defaultUrl)
                Toast.makeText(context, "已重置为默认网址", Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    override fun onResume() {
        super.onResume()
        setupImmersiveMode()
        webView.onResume()
    }

    override fun onPause() {
        super.onPause()
        webView.onPause()
    }

    override fun onDestroy() {
        webView.destroy()
        super.onDestroy()
    }
}
