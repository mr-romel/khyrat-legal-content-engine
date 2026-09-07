package com.khyrat.marketplace

import android.app.Activity
import android.os.Bundle
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView

class MainActivity : Activity() {
    private val defaultUrl = "http://10.0.2.2:8766/mobile/"
    private lateinit var web: WebView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefs = getSharedPreferences("marketplace", MODE_PRIVATE)
        val saved = prefs.getString("server_url", defaultUrl) ?: defaultUrl
        showSetup(saved)
    }

    private fun showSetup(saved: String) {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 32)
        }
        box.addView(TextView(this).apply { text = "خيرت Marketplace"; textSize = 24f })
        box.addView(TextView(this).apply { text = "عنوان خادم الداشبورد على الـ PC أو Quick Tunnel"; textSize = 16f })
        val input = EditText(this).apply { setText(saved); hint = "http://192.168.1.10:8766/mobile/" }
        box.addView(input)
        box.addView(Button(this).apply {
            text = "فتح الداشبورد"
            setOnClickListener {
                var url = input.text.toString().trim()
                if (!url.endsWith("/")) url += "/"
                getSharedPreferences("marketplace", MODE_PRIVATE).edit().putString("server_url", url).apply()
                openDashboard(url)
            }
        })
        setContentView(box)
    }

    private fun openDashboard(url: String) {
        web = WebView(this)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.webViewClient = WebViewClient()
        web.loadUrl(url)
        setContentView(web)
    }
}
