$logFile = Join-Path $PSScriptRoot "tunnel_url.txt"
$serverUrl = "http://localhost:8000"

# Check if server is running
try {
    $null = Invoke-RestMethod -Uri "$serverUrl/api/health" -TimeoutSec 3
} catch {
    Write-Host "Servidor nao esta rodando na porta 8000. Iniciando..."
    Set-Location $PSScriptRoot
    Start-Process -WindowStyle Hidden -FilePath "python" -ArgumentList "main.py"
    Start-Sleep -Seconds 3
}

Write-Host "Conectando ao serveo.net (tunel gratis)..." -ForegroundColor Cyan

# Start SSH tunnel to serveo.net
$job = Start-Job -ScriptBlock {
    param($logPath)
    ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R 80:localhost:8000 serveo.net 2>&1 | ForEach-Object {
        if ($_ -match "(https://[^\s]+)") {
            $url = $matches[1]
            $url | Out-File -FilePath $logPath -Encoding UTF8
            Write-Host "`nURL PUBLICA: $url" -ForegroundColor Green
            Write-Host "Admin: $url/admin" -ForegroundColor Green
            Write-Host "`nCole essa URL no app Android!" -ForegroundColor Yellow
        }
        $_
    }
} -ArgumentList $logFile

Start-Sleep -Seconds 8

# Show URL if found
if (Test-Path $logFile) {
    $url = Get-Content $logFile -Raw
    Write-Host "`n==========================================" -ForegroundColor Cyan
    Write-Host "  SERVIDOR ONLINE!" -ForegroundColor Green
    Write-Host "  URL: $url" -ForegroundColor White
    Write-Host "  Admin: ${url}admin" -ForegroundColor White
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "`nPressione qualquer tecla para parar..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    Stop-Job $job
    Remove-Job $job
} else {
    Write-Host "Aguardando tunel... (pressione CTRL+C para cancelar)" -ForegroundColor Yellow
    $job | Wait-Job
    Receive-Job $job
}
