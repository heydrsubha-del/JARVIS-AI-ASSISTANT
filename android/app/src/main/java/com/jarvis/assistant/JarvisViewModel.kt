package com.jarvis.assistant

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.auth.FirebaseAuth
import io.livekit.android.LiveKit
import io.livekit.android.room.Room
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class PendingConfirmation(
    val id: String,
    val title: String,
    val detail: String,
)

class JarvisViewModel(application: Application) : AndroidViewModel(application) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(12, TimeUnit.SECONDS)
        .callTimeout(15, TimeUnit.SECONDS)
        .build()
    private val jsonType = "application/json; charset=utf-8".toMediaType()
    private var room: Room? = null
    private var pollJob: kotlinx.coroutines.Job? = null

    private val _status = MutableStateFlow("Ready")
    val status: StateFlow<String> = _status.asStateFlow()
    private val _connected = MutableStateFlow(false)
    val connected: StateFlow<Boolean> = _connected.asStateFlow()
    private val _muted = MutableStateFlow(false)
    val muted: StateFlow<Boolean> = _muted.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()
    private val _confirmation = MutableStateFlow<PendingConfirmation?>(null)
    val confirmation: StateFlow<PendingConfirmation?> = _confirmation.asStateFlow()

    private fun ensureFirebase(): FirebaseAuth? {
        return try {
            val context = getApplication<Application>()
            val app = if (FirebaseApp.getApps(context).isNotEmpty()) {
                FirebaseApp.getInstance()
            } else {
                if (BuildConfig.FIREBASE_API_KEY.isBlank() ||
                    BuildConfig.FIREBASE_APPLICATION_ID.isBlank() ||
                    BuildConfig.FIREBASE_PROJECT_ID.isBlank()) return null
                val options = FirebaseOptions.Builder()
                    .setApiKey(BuildConfig.FIREBASE_API_KEY)
                    .setApplicationId(BuildConfig.FIREBASE_APPLICATION_ID)
                    .setProjectId(BuildConfig.FIREBASE_PROJECT_ID)
                    .build()
                FirebaseApp.initializeApp(context, options)
                    ?: throw IllegalStateException("Firebase initialization failed")
            }
            FirebaseAuth.getInstance(app)
        } catch (e: Exception) {
            Log.e("JARVIS", "Firebase initialization failed", e)
            null
        }
    }

    private suspend fun idToken(): String? {
        val auth = ensureFirebase() ?: return null
        if (auth.currentUser == null) auth.signInAnonymously().await()
        return auth.currentUser?.getIdToken(false)?.await()?.token
    }

    private suspend fun apiRequest(path: String, method: String = "GET", body: JSONObject? = null): JSONObject {
        val token = idToken()
        val base = BuildConfig.API_BASE_URL.trimEnd('/')
        val builder = Request.Builder().url(base + path)
        if (!token.isNullOrBlank()) builder.header("Authorization", "Bearer $token")
        // Development mode only: backend ignores X-Dev-User when AUTH_MODE=firebase.
        if (token.isNullOrBlank()) builder.header("X-Dev-User", "android-local-user")
        if (method == "POST") {
            builder.post((body ?: JSONObject()).toString().toRequestBody(jsonType))
        } else {
            builder.get()
        }
        return withContext(Dispatchers.IO) {
            client.newCall(builder.build()).execute().use { response ->
                val text = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    val detail = runCatching { JSONObject(text).optString("detail") }.getOrNull()
                    throw IOException(detail?.takeIf { it.isNotBlank() } ?: "API request failed (${response.code})")
                }
                if (text.isBlank()) JSONObject() else JSONObject(text)
            }
        }
    }

    fun connect() {
        if (_connected.value) return
        viewModelScope.launch {
            _error.value = null
            _status.value = "Connecting to cloud…"
            try {
                val sessionInfo = withContext(Dispatchers.IO) { apiRequest("/api/session", "POST") }
                val url = sessionInfo.getString("url")
                val token = sessionInfo.getString("token")
                val liveRoom = LiveKit.create(getApplication<Application>().applicationContext)
                room = liveRoom
                liveRoom.connect(url, token)
                val enabled = liveRoom.localParticipant.setMicrophoneEnabled(true)
                if (!enabled) throw IOException("The microphone could not be enabled")
                _connected.value = true
                _muted.value = false
                _status.value = "Listening · cloud connected"
                startConfirmationPolling()
            } catch (e: Exception) {
                _error.value = e.message ?: "Could not connect to JARVIS"
                _status.value = "Connection failed"
                disconnectInternal()
            }
        }
    }

    fun disconnect() {
        viewModelScope.launch { disconnectInternal() }
    }

    private suspend fun disconnectInternal() {
        pollJob?.cancel()
        pollJob = null
        runCatching { room?.localParticipant?.setMicrophoneEnabled(false) }
        runCatching { room?.disconnect() }
        room = null
        _connected.value = false
        _muted.value = false
        _confirmation.value = null
        _status.value = "Ready"
    }

    fun toggleMute() {
        viewModelScope.launch {
            val liveRoom = room ?: return@launch
            try {
                val newValue = !_muted.value
                liveRoom.localParticipant.setMicrophoneEnabled(!newValue)
                _muted.value = newValue
                _status.value = if (newValue) "Microphone muted" else "Listening · cloud connected"
            } catch (e: Exception) {
                _error.value = e.message ?: "Could not change microphone state"
            }
        }
    }

    private fun startConfirmationPolling() {
        pollJob?.cancel()
        pollJob = viewModelScope.launch {
            while (isActive && _connected.value) {
                try {
                    val result = apiRequest("/api/confirmations/pending")
                    val items = result.optJSONArray("items")
                    val first = items?.optJSONObject(0)
                    _confirmation.value = if (first != null) {
                        val payload = first.optJSONObject("payload")
                        val automation = payload?.optString("automation_id", "Home automation") ?: "Home automation"
                        PendingConfirmation(
                            id = first.getString("id"),
                            title = "Run home automation?",
                            detail = "JARVIS wants to run $automation. This request expires shortly.",
                        )
                    } else null
                } catch (e: Exception) {
                    // Temporary polling errors should not end an active voice session.
                    Log.w("JARVIS", "Confirmation polling failed: ${e.message}")
                }
                delay(2500)
            }
        }
    }

    fun answerConfirmation(confirm: Boolean) {
        val pending = _confirmation.value ?: return
        viewModelScope.launch {
            try {
                val response = apiRequest(
                    "/api/confirmations/${pending.id}",
                    "POST",
                    JSONObject().put("confirm", confirm),
                )
                _status.value = when {
                    !confirm -> "Automation cancelled"
                    response.optBoolean("ok") -> "Automation completed"
                    else -> "Automation failed"
                }
                _confirmation.value = null
            } catch (e: Exception) {
                _error.value = e.message ?: "Could not submit confirmation"
                _confirmation.value = null
            }
        }
    }

    override fun onCleared() {
        pollJob?.cancel()
        room?.disconnect()
        room = null
        super.onCleared()
    }
}
