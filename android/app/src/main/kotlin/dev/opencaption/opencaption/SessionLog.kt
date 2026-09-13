package dev.opencaption.opencaption

import android.content.ContentValues
import android.os.Build
import android.os.Environment
import android.os.ParcelFileDescriptor
import android.provider.MediaStore
import android.util.Log
import java.io.File
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

internal class SessionLog(private val activity: MainActivity) {
    private val enabled = BuildConfig.DIAGNOSTICS_ENABLED
    private val previousCrashHandler = Thread.getDefaultUncaughtExceptionHandler()
    private val crashHandler = Thread.UncaughtExceptionHandler { thread, error ->
        write("uncaught_exception thread=${thread.name}", error)
        previousCrashHandler?.uncaughtException(thread, error)
    }
    private var descriptor: ParcelFileDescriptor? = null
    private var output: FileOutputStream? = null

    @Volatile
    var fd: Int = -1
        private set

    init {
        Thread.setDefaultUncaughtExceptionHandler(crashHandler)
    }

    @Synchronized
    fun begin() {
        if (!enabled) {
            close()
            return
        }
        close()
        val name = "opencaption_${SimpleDateFormat("yyyyMMddHHmmss", Locale.US).format(Date())}.log"
        try {
            descriptor = if (Build.VERSION.SDK_INT >= 29) {
                val values = ContentValues().apply {
                    put(MediaStore.MediaColumns.DISPLAY_NAME, name)
                    put(MediaStore.MediaColumns.MIME_TYPE, "text/plain")
                    put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                }
                val uri = checkNotNull(
                    activity.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values),
                )
                activity.contentResolver.openFileDescriptor(uri, "w")
            } else {
                val directory = activity.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
                    ?: activity.filesDir
                directory.mkdirs()
                ParcelFileDescriptor.open(
                    File(directory, name),
                    ParcelFileDescriptor.MODE_CREATE or
                        ParcelFileDescriptor.MODE_TRUNCATE or
                        ParcelFileDescriptor.MODE_WRITE_ONLY,
                )
            }
            fd = descriptor?.fd ?: -1
            output = descriptor?.let { FileOutputStream(it.fileDescriptor) }
            write("log_created file=$name")
            write("device=${Build.MANUFACTURER}/${Build.MODEL} sdk=${Build.VERSION.SDK_INT} abi=${Build.SUPPORTED_ABIS.joinToString()}")
        } catch (error: Throwable) {
            Log.e(TAG, "Unable to create diagnostic log", error)
            close()
        }
    }

    @Synchronized
    fun write(message: String, error: Throwable? = null) {
        if (!enabled) return
        val timestamp = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US).format(Date())
        val details = if (error == null) message else "$message ${Log.getStackTraceString(error)}"
        Log.i(TAG, details)
        try {
            output?.write("$timestamp [${Thread.currentThread().name}] $details\n".toByteArray(Charsets.UTF_8))
            output?.flush()
        } catch (writeError: Throwable) {
            Log.e(TAG, "Unable to append diagnostic log", writeError)
        }
    }

    @Synchronized
    fun close() {
        fd = -1
        try {
            output?.flush()
        } catch (_: Throwable) {
        }
        try {
            output?.close()
        } catch (_: Throwable) {
        }
        try {
            descriptor?.close()
        } catch (_: Throwable) {
        }
        output = null
        descriptor = null
    }

    fun uninstallCrashHandler() {
        if (Thread.getDefaultUncaughtExceptionHandler() === crashHandler) {
            Thread.setDefaultUncaughtExceptionHandler(previousCrashHandler)
        }
    }

    private companion object {
        const val TAG = "OpenCaption"
    }
}
