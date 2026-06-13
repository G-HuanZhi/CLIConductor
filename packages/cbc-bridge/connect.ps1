# PowerShell WebSocket terminal client for CBC Bridge
# Run this in a REAL terminal (Windows Terminal / PowerShell window)
# to connect to the shared cbc session.

param(
  [string]$Server = "localhost",
  [int]$Port = 6789
)

Add-Type -AssemblyName System.Net.WebSockets

$ws = New-Object System.Net.WebSockets.ClientWebSocket
$uri = "ws://${Server}:${Port}"

try {
  $ct = New-Object System.Threading.CancellationToken
  $ws.ConnectAsync($uri, $ct).Wait()

  Write-Host "Connected to CBC Bridge (Ctrl+C to detach)" -ForegroundColor Green

  # Read from WS → stdout (background job)
  $job = Start-Job -ScriptBlock {
    param($Socket)
    $tok = New-Object System.Threading.CancellationToken
    $buf = New-Object byte[] 4096
    $seg = New-Object System.ArraySegment[byte]($buf)
    try {
      while ($Socket.State -eq 'Open') {
        $res = $Socket.ReceiveAsync($seg, $tok)
        $res.Wait()
        if ($res.Result.Count -gt 0) {
          $text = [System.Text.Encoding]::UTF8.GetString($buf, 0, $res.Result.Count)
          Write-Host -NoNewline $text
        }
      }
    } catch { }
  } -ArgumentList $ws

  # Read from stdin → WS (main thread)
  while ($ws.State -eq 'Open') {
    $key = [System.Console]::ReadKey($true)  # intercept = true
    $ch = $key.KeyChar
    if ($ch -ne 0) {
      $b = [System.Text.Encoding]::UTF8.GetBytes($ch.ToString())
      $seg = New-Object System.ArraySegment[byte]($b)
      $ws.SendAsync($seg, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
    } else {
      # Special keys
      switch ($key.Key) {
        "Enter"   { $b = "`r"; break }
        "Tab"     { $b = "`t"; break }
        "Backspace" { $b = "`b"; break }
        "Escape"  { $b = "`e"; break }
        default   { continue }
      }
      $seg = New-Object System.ArraySegment[byte]([System.Text.Encoding]::UTF8.GetBytes($b))
      $ws.SendAsync($seg, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
    }
  }

} catch {
  Write-Host "Error: $_" -ForegroundColor Red
} finally {
  if ($ws.State -eq 'Open') { $ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "bye", $ct).Wait() }
  $ws.Dispose()
  Stop-Job $job -ErrorAction SilentlyContinue
  Remove-Job $job -ErrorAction SilentlyContinue
}
