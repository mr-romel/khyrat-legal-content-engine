package com.khyrat.marketplace

import android.app.Activity
import android.os.Bundle
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast

class MainActivity : Activity() {
    private val defaultUrl = "http://127.0.0.1:8766/mobile/"
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val web = WebView(this)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.webViewClient = WebViewClient()
        web.loadUrl(defaultUrl)
        setContentView(web)
        Toast.makeText(this, "للموبايل خارج نفس الجهاز غيّر عنوان الخادم إلى عنوان الـ PC أو Quick Tunnel.", Toast.LENGTH_LONG).show()
    }
}
