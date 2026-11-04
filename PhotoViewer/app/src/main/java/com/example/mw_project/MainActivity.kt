package com.example.mw_project

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONArray
import java.io.File
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.*

// 서버 주소: 클라우드(PythonAnywhere) 배포 주소
const val SITE_URL = "https://pyr.pythonanywhere.com"

data class Post(
    val id: Int,
    val author: Int,
    val authorName: String,
    val title: String,
    val text: String,
    val publishedDate: String,
    val imageUrl: String?
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    PhotoBlogScreen()
                }
            }
        }
    }
}

@Composable
fun PhotoBlogScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val client = remember { OkHttpClient() }

    var posts by remember { mutableStateOf<List<Post>>(emptyList()) }
    var statusText by remember { mutableStateOf("동기화 버튼을 눌러주세요") }
    var showUploadDialog by remember { mutableStateOf(false) }

    // 요구사항 3: 상세화면 전환용 상태. null이면 목록, 아니면 해당 Post 상세
    var selectedPost by remember { mutableStateOf<Post?>(null) }
    // 요구사항 3: 수정 다이얼로그 표시 여부
    var showEditDialog by remember { mutableStateOf(false) }

    fun syncPosts() {
        scope.launch {
            statusText = "동기화 중..."
            try {
                val result = withContext(Dispatchers.IO) {
                    val request = Request.Builder().url("$SITE_URL/api_root/Post/").build()
                    client.newCall(request).execute().use { response ->
                        val body = response.body?.string() ?: "[]"
                        val arr = JSONArray(body)
                        (0 until arr.length()).map { i ->
                            val obj = arr.getJSONObject(i)
                            Post(
                                id = obj.optInt("id"),
                                author = obj.optInt("author"),
                                authorName = obj.optString("author_name"),
                                title = obj.optString("title"),
                                text = obj.optString("text"),
                                publishedDate = obj.optString("published_date"),
                                imageUrl = obj.optString("image", null)
                            )
                        }
                    }
                }
                // 요구사항 2: 최신 게시글이 먼저 오도록 (published_date 내림차순)
                posts = result.sortedByDescending { it.publishedDate }
                statusText = if (result.isEmpty()) "불러올 이미지가 없습니다." else "이미지 로드 성공!"
            } catch (e: Exception) {
                statusText = "동기화 실패: ${e.message}"
            }
        }
    }

    fun deletePost(post: Post) {
        scope.launch {
            statusText = "삭제 중..."
            try {
                withContext(Dispatchers.IO) {
                    val request = Request.Builder()
                        .url("$SITE_URL/api_root/Post/${post.id}/")
                        .delete()
                        .build()
                    client.newCall(request).execute().use { response ->
                        if (!response.isSuccessful) {
                            throw Exception("서버 응답 ${response.code}")
                        }
                    }
                }
                statusText = "삭제 완료"
                selectedPost = null
                syncPosts()
            } catch (e: Exception) {
                statusText = "삭제 실패: ${e.message}"
            }
        }
    }

    fun uploadPost(title: String, text: String, imageUri: Uri?) {
        scope.launch {
            statusText = "업로드 중..."
            try {
                withContext(Dispatchers.IO) {
                    val now = SimpleDateFormat(
                        "yyyy-MM-dd'T'HH:mm:ssXXX", Locale.getDefault()
                    ).format(Date())

                    val bodyBuilder = MultipartBody.Builder()
                        .setType(MultipartBody.FORM)
                        .addFormDataPart("author", "1")
                        .addFormDataPart("title", title)
                        .addFormDataPart("text", text)
                        .addFormDataPart("created_date", now)
                        .addFormDataPart("published_date", now)

                    if (imageUri != null) {
                        val inputStream = context.contentResolver.openInputStream(imageUri)
                        val tempFile = File(context.cacheDir, "upload_temp.jpg")
                        FileOutputStream(tempFile).use { out -> inputStream?.copyTo(out) }
                        bodyBuilder.addFormDataPart(
                            "image", tempFile.name,
                            tempFile.asRequestBody("image/jpeg".toMediaTypeOrNull())
                        )
                    }

                    val request = Request.Builder()
                        .url("$SITE_URL/api_root/Post/")
                        .post(bodyBuilder.build())
                        .build()

                    client.newCall(request).execute().use { response ->
                        if (!response.isSuccessful) {
                            throw Exception("서버 응답 ${response.code}: ${response.body?.string()}")
                        }
                    }
                }
                statusText = "업로드 성공!"
                showUploadDialog = false
                syncPosts()
            } catch (e: Exception) {
                statusText = "업로드 실패: ${e.message}"
            }
        }
    }

    // 요구사항 3: 수정 - title/text 갱신 (이미지는 선택 시에만 변경)
    fun editPost(post: Post, title: String, text: String, imageUri: Uri?) {
        scope.launch {
            statusText = "수정 중..."
            try {
                withContext(Dispatchers.IO) {
                    val bodyBuilder = MultipartBody.Builder()
                        .setType(MultipartBody.FORM)
                        .addFormDataPart("title", title)
                        .addFormDataPart("text", text)

                    if (imageUri != null) {
                        val inputStream = context.contentResolver.openInputStream(imageUri)
                        val tempFile = File(context.cacheDir, "edit_temp.jpg")
                        FileOutputStream(tempFile).use { out -> inputStream?.copyTo(out) }
                        bodyBuilder.addFormDataPart(
                            "image", tempFile.name,
                            tempFile.asRequestBody("image/jpeg".toMediaTypeOrNull())
                        )
                    }

                    val request = Request.Builder()
                        .url("$SITE_URL/api_root/Post/${post.id}/")
                        .patch(bodyBuilder.build())
                        .build()

                    client.newCall(request).execute().use { response ->
                        if (!response.isSuccessful) {
                            throw Exception("서버 응답 ${response.code}: ${response.body?.string()}")
                        }
                    }
                }
                statusText = "수정 완료!"
                showEditDialog = false
                selectedPost = null
                syncPosts()
            } catch (e: Exception) {
                statusText = "수정 실패: ${e.message}"
            }
        }
    }

    fun sharePost(post: Post) {
        val link = "$SITE_URL/post/${post.id}/"
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, link)
        }
        context.startActivity(Intent.createChooser(intent, "게시글 공유"))
    }

    if (selectedPost != null) {
        // 요구사항 3: 상세화면 (title, 게시자, text, date, 수정/삭제) + 요구사항 4: 공유
        PostDetailScreen(
            post = selectedPost!!,
            onBack = { selectedPost = null },
            onEdit = { showEditDialog = true },
            onDelete = { deletePost(selectedPost!!) },
            onShare = { sharePost(selectedPost!!) }
        )

        if (showEditDialog) {
            PostFormDialog(
                title = "게시글 수정",
                initialTitle = selectedPost!!.title,
                initialText = selectedPost!!.text,
                requireImage = false,
                onDismiss = { showEditDialog = false },
                onSubmit = { t, txt, uri -> editPost(selectedPost!!, t, txt, uri) }
            )
        }
    } else {
        // 요구사항 1: 목록 화면 - title, 게시자, date만 표시
        Column(modifier = Modifier.fillMaxSize().padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Button(onClick = { syncPosts() }, modifier = Modifier.weight(1f)) {
                    Text("동기화")
                }
                Button(onClick = { showUploadDialog = true }, modifier = Modifier.weight(1f)) {
                    Text("Upload")
                }
            }

            Spacer(modifier = Modifier.height(8.dp))
            Text(statusText)
            Spacer(modifier = Modifier.height(8.dp))

            LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                items(posts) { post ->
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { selectedPost = post }
                            .padding(vertical = 8.dp)
                    ) {
                        Text(post.title, style = MaterialTheme.typography.titleMedium)
                        Text("게시자: ${post.authorName}", style = MaterialTheme.typography.bodySmall)
                        Text(post.publishedDate, style = MaterialTheme.typography.bodySmall)
                    }
                    Divider()
                }
            }
        }

        if (showUploadDialog) {
            PostFormDialog(
                title = "Upload",
                initialTitle = "",
                initialText = "",
                requireImage = true,
                onDismiss = { showUploadDialog = false },
                onSubmit = { t, txt, uri -> uploadPost(t, txt, uri) }
            )
        }
    }
}

// 요구사항 3: 게시글 상세화면 - title, 게시자, text, date, 수정/삭제 + 공유 버튼
@Composable
fun PostDetailScreen(
    post: Post,
    onBack: () -> Unit,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
    onShare: () -> Unit
) {
    var showDeleteConfirm by remember { mutableStateOf(false) }

    Column(modifier = Modifier.fillMaxSize().padding(12.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TextButton(onClick = onBack) { Text("< 목록으로") }
        }
        Spacer(modifier = Modifier.height(8.dp))

        if (!post.imageUrl.isNullOrEmpty()) {
            AsyncImage(
                model = post.imageUrl,
                contentDescription = post.title,
                modifier = Modifier.fillMaxWidth().height(260.dp),
                contentScale = ContentScale.Crop
            )
            Spacer(modifier = Modifier.height(8.dp))
        }

        Text(post.title, style = MaterialTheme.typography.headlineSmall)
        Text("게시자: ${post.authorName}", style = MaterialTheme.typography.bodyMedium)
        Text(post.publishedDate, style = MaterialTheme.typography.bodySmall)

        Spacer(modifier = Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = onEdit) { Text("수정") }
            Button(onClick = { showDeleteConfirm = true }) { Text("삭제") }
            Button(onClick = onShare) { Text("공유") }
        }

        Spacer(modifier = Modifier.height(12.dp))
        Text(post.text)
    }

    if (showDeleteConfirm) {
        AlertDialog(
            onDismissRequest = { showDeleteConfirm = false },
            title = { Text("게시글 삭제") },
            text = { Text("'${post.title}' 게시글을 삭제하시겠습니까?") },
            confirmButton = {
                TextButton(onClick = {
                    showDeleteConfirm = false
                    onDelete()
                }) { Text("삭제") }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteConfirm = false }) { Text("취소") }
            }
        )
    }
}

// 업로드/수정 공용 다이얼로그: initialTitle/initialText가 있으면 수정 모드로 동작
@Composable
fun PostFormDialog(
    title: String,
    initialTitle: String,
    initialText: String,
    requireImage: Boolean,
    onDismiss: () -> Unit,
    onSubmit: (title: String, text: String, imageUri: Uri?) -> Unit
) {
    var titleInput by remember { mutableStateOf(initialTitle) }
    var textInput by remember { mutableStateOf(initialText) }
    var selectedImageUri by remember { mutableStateOf<Uri?>(null) }

    val pickImageLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetContent()
    ) { uri: Uri? -> selectedImageUri = uri }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = titleInput,
                    onValueChange = { titleInput = it },
                    label = { Text("Title") },
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = textInput,
                    onValueChange = { textInput = it },
                    label = { Text("Text") },
                    modifier = Modifier.fillMaxWidth()
                )
                Button(onClick = { pickImageLauncher.launch("image/*") }) {
                    Text(if (selectedImageUri == null) "이미지 선택" else "이미지 선택됨")
                }
                selectedImageUri?.let {
                    AsyncImage(
                        model = it,
                        contentDescription = null,
                        modifier = Modifier.fillMaxWidth().height(150.dp),
                        contentScale = ContentScale.Crop
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onSubmit(titleInput, textInput, selectedImageUri) },
                enabled = titleInput.isNotBlank() && (!requireImage || selectedImageUri != null)
            ) { Text(title) }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("취소") }
        }
    )
}
