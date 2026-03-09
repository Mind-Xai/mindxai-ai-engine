try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/chat?prompt=ping" -Method Post | Out-Null
} catch {
}