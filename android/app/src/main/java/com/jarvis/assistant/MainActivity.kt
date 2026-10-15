package com.jarvis.assistant

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { JarvisTheme { JarvisScreen() } }
    }
}

@Composable
private fun JarvisTheme(content: @Composable () -> Unit) {
    val colors = darkColorScheme(
        primary = Color(0xFF72D6FF),
        secondary = Color(0xFF9BA9FF),
        background = Color(0xFF080D17),
        surface = Color(0xFF111A2A),
        onBackground = Color(0xFFE7F0FF),
        onSurface = Color(0xFFE7F0FF),
    )
    MaterialTheme(colorScheme = colors, content = content)
}

@Composable
private fun JarvisScreen(vm: JarvisViewModel = viewModel()) {
    val context = LocalContext.current
    val connected by vm.connected.collectAsState()
    val muted by vm.muted.collectAsState()
    val status by vm.status.collectAsState()
    val error by vm.error.collectAsState()
    val confirmation by vm.confirmation.collectAsState()
    var permissionGranted = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) vm.connect()
    }

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            modifier = Modifier.fillMaxSize().padding(horizontal = 24.dp, vertical = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text("JARVIS", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.height(6.dp))
            Text("Your cloud voice assistant", style = MaterialTheme.typography.bodyLarge, color = Color(0xFF9EADC4))
            Spacer(Modifier.height(48.dp))
            Box(
                modifier = Modifier.size(188.dp).background(
                    color = if (connected && !muted) Color(0xFF123650) else Color(0xFF17243A),
                    shape = CircleShape,
                ),
                contentAlignment = Alignment.Center,
            ) {
                Text(if (!connected) "J" else if (muted) "Ⅱ" else "〰", style = MaterialTheme.typography.displayLarge, color = MaterialTheme.colorScheme.primary)
            }
            Spacer(Modifier.height(28.dp))
            Text(status, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
            Spacer(Modifier.height(28.dp))
            if (!connected) {
                Button(
                    onClick = {
                        if (permissionGranted) vm.connect() else permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                    },
                    modifier = Modifier.fillMaxWidth().height(54.dp),
                ) { Text("Connect to JARVIS") }
            } else {
                Button(onClick = { vm.toggleMute() }, modifier = Modifier.fillMaxWidth().height(54.dp)) {
                    Text(if (muted) "Unmute microphone" else "Mute microphone")
                }
                Spacer(Modifier.height(10.dp))
                OutlinedButton(onClick = { vm.disconnect() }, modifier = Modifier.fillMaxWidth().height(50.dp)) {
                    Text("Disconnect")
                }
            }
            if (error != null) {
                Spacer(Modifier.height(16.dp))
                Text(error!!, color = MaterialTheme.colorScheme.error, textAlign = TextAlign.Center, style = MaterialTheme.typography.bodyMedium)
            }
            Spacer(Modifier.height(28.dp))
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                Column(Modifier.fillMaxWidth().padding(16.dp)) {
                    Text("Wake word", fontWeight = FontWeight.SemiBold)
                    Text("Placeholder only — hands-free wake detection is not enabled.", color = Color(0xFF9EADC4), style = MaterialTheme.typography.bodySmall)
                }
            }
            Spacer(Modifier.height(12.dp))
            Text("Audio is streamed to the cloud. Keep this screen open during the MVP session.", color = Color(0xFF7F8DA4), style = MaterialTheme.typography.bodySmall, textAlign = TextAlign.Center)
        }
    }

    if (confirmation != null) {
        AlertDialog(
            onDismissRequest = { vm.answerConfirmation(false) },
            title = { Text(confirmation!!.title) },
            text = { Text(confirmation!!.detail) },
            confirmButton = { TextButton(onClick = { vm.answerConfirmation(true) }) { Text("Confirm") } },
            dismissButton = { TextButton(onClick = { vm.answerConfirmation(false) }) { Text("Cancel") } },
        )
    }
}
