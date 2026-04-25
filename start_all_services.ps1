$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $RootDir ".run_logs"
$VisBackendDir = Join-Path $RootDir "backend\vis\digital_twins\mock_backend"
$VisFrontendDir = Join-Path $RootDir "backend\vis\digital_twins\frontend"
$McpDir = Join-Path $RootDir "mcp"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

$script:TrackedProcesses = @()

function Require-Path {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing required path: $Path"
    }
}

function Resolve-CondaCommand {
    $cmd = Get-Command conda -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $candidates = @(
        "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
        "$env:USERPROFILE\anaconda3\condabin\conda.bat",
        "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
        "$env:USERPROFILE\miniconda3\condabin\conda.bat",
        "$env:USERPROFILE\opt\anaconda3\Scripts\conda.exe",
        "$env:USERPROFILE\opt\anaconda3\condabin\conda.bat",
        "C:\ProgramData\anaconda3\Scripts\conda.exe",
        "C:\ProgramData\anaconda3\condabin\conda.bat",
        "C:\ProgramData\miniconda3\Scripts\conda.exe",
        "C:\ProgramData\miniconda3\condabin\conda.bat"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    throw "Could not find conda. Please install Anaconda/Miniconda or add conda to PATH."
}

function Enable-CondaEnv {
    param(
        [string]$CondaCommand,
        [string]$EnvName
    )

    $hook = & $CondaCommand "shell.powershell" "hook" 2>$null | Out-String
    if (-not $hook.Trim()) {
        throw "Failed to initialize conda PowerShell hook from: $CondaCommand"
    }

    Invoke-Expression $hook
    conda activate $EnvName
}

function Test-HttpReady {
    param(
        [string]$Name,
        [string]$Url,
        [int]$Attempts = 40,
        [int]$DelaySeconds = 1
    )

    for ($i = 0; $i -lt $Attempts; $i++) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 | Out-Null
            Write-Host "[ok] $Name is ready: $Url"
            return $true
        } catch {
            Start-Sleep -Seconds $DelaySeconds
        }
    }

    Write-Warning "$Name did not become ready in time: $Url"
    return $false
}

function Start-LoggedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$StdOutLog,
        [string]$StdErrLog
    )

    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $StdOutLog `
        -RedirectStandardError $StdErrLog `
        -PassThru

    $script:TrackedProcesses += [pscustomobject]@{
        Name = $Name
        Process = $process
        StdOutLog = $StdOutLog
        StdErrLog = $StdErrLog
    }

    Write-Host "[start] $Name (pid=$($process.Id))"
    Write-Host "        stdout: $StdOutLog"
    Write-Host "        stderr: $StdErrLog"

    return $process
}

function Stop-AllTrackedProcesses {
    foreach ($entry in $script:TrackedProcesses) {
        $process = $entry.Process
        if ($process -and -not $process.HasExited) {
            try {
                Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            } catch {
            }
        }
    }
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$visBackendOut = Join-Path $LogDir "vis_backend_${Timestamp}.out.log"
$visBackendErr = Join-Path $LogDir "vis_backend_${Timestamp}.err.log"
$visFrontendOut = Join-Path $LogDir "vis_frontend_${Timestamp}.out.log"
$visFrontendErr = Join-Path $LogDir "vis_frontend_${Timestamp}.err.log"
$deviceLlmOut = Join-Path $LogDir "device_llm_server_${Timestamp}.out.log"
$deviceLlmErr = Join-Path $LogDir "device_llm_server_${Timestamp}.err.log"
$mcpPipeOut = Join-Path $LogDir "mcp_pipe_${Timestamp}.out.log"
$mcpPipeErr = Join-Path $LogDir "mcp_pipe_${Timestamp}.err.log"

Require-Path (Join-Path $VisBackendDir "app.py")
Require-Path (Join-Path $VisFrontendDir "package.json")
Require-Path (Join-Path $McpDir "device_llm_server.py")
Require-Path (Join-Path $McpDir "mcp_pipe.py")

if (-not $env:MCP_ENDPOINT) {
    $mcpEnvPath = Join-Path $McpDir ".env"
    if (-not (Test-Path -LiteralPath $mcpEnvPath)) {
        throw "MCP_ENDPOINT is not set, and $mcpEnvPath was not found."
    }
}

$condaCommand = Resolve-CondaCommand
Enable-CondaEnv -CondaCommand $condaCommand -EnvName "py312"

$env:PYTHONUNBUFFERED = "1"
if (-not $env:MCP_CONFIG) {
    $env:MCP_CONFIG = Join-Path $McpDir "mcp_config.json"
}

$pythonCommand = (Get-Command python -ErrorAction Stop).Source
$npmCommand = (Get-Command npm -ErrorAction Stop).Source

if (-not (Test-Path -LiteralPath (Join-Path $VisFrontendDir "node_modules"))) {
    Write-Host "[info] frontend\node_modules is missing. Running npm install once..."
    Push-Location $VisFrontendDir
    try {
        & $npmCommand install
    } finally {
        Pop-Location
    }
}

Write-Host "[info] Using python: $pythonCommand"
Write-Host "[info] Using npm   : $npmCommand"
Write-Host "[info] Logs dir    : $LogDir"

$null = Start-LoggedProcess `
    -Name "visualization backend" `
    -FilePath $pythonCommand `
    -ArgumentList @("-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8787") `
    -WorkingDirectory $VisBackendDir `
    -StdOutLog $visBackendOut `
    -StdErrLog $visBackendErr

Test-HttpReady -Name "visualization backend" -Url "http://127.0.0.1:8787/api/v1/health" -Attempts 30 -DelaySeconds 1 | Out-Null

$null = Start-LoggedProcess `
    -Name "device llm server" `
    -FilePath $pythonCommand `
    -ArgumentList @("device_llm_server.py") `
    -WorkingDirectory $McpDir `
    -StdOutLog $deviceLlmOut `
    -StdErrLog $deviceLlmErr

Test-HttpReady -Name "device llm server" -Url "http://127.0.0.1:12345/health" -Attempts 30 -DelaySeconds 1 | Out-Null

$null = Start-LoggedProcess `
    -Name "mcp pipe" `
    -FilePath $pythonCommand `
    -ArgumentList @("mcp_pipe.py") `
    -WorkingDirectory $McpDir `
    -StdOutLog $mcpPipeOut `
    -StdErrLog $mcpPipeErr

Start-Sleep -Seconds 3

$null = Start-LoggedProcess `
    -Name "visualization frontend" `
    -FilePath $npmCommand `
    -ArgumentList @("run", "dev", "--", "--host", "0.0.0.0", "--port", "5173") `
    -WorkingDirectory $VisFrontendDir `
    -StdOutLog $visFrontendOut `
    -StdErrLog $visFrontendErr

Test-HttpReady -Name "visualization frontend" -Url "http://127.0.0.1:5173" -Attempts 40 -DelaySeconds 1 | Out-Null

Write-Host ""
Write-Host "Services started."
Write-Host "  Visualization frontend: http://127.0.0.1:5173"
Write-Host "  Visualization backend : http://127.0.0.1:8787"
Write-Host "  Device LLM server     : http://127.0.0.1:12345/health"
Write-Host "  MCP stdout log        : $mcpPipeOut"
Write-Host ""
Write-Host "Press Ctrl+C to stop all services."

try {
    while ($true) {
        Start-Sleep -Seconds 1

        $exited = $script:TrackedProcesses | Where-Object { $_.Process.HasExited }
        if ($exited) {
            foreach ($entry in $exited) {
                Write-Warning "$($entry.Name) exited with code $($entry.Process.ExitCode)."
                Write-Warning "stdout: $($entry.StdOutLog)"
                Write-Warning "stderr: $($entry.StdErrLog)"
            }
            break
        }
    }
} finally {
    Write-Host ""
    Write-Host "Stopping all services..."
    Stop-AllTrackedProcesses
}
