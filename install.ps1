# YuE2 Musik-Generator - Installation (Windows, NVIDIA RTX 50xx / CUDA 12.8)
# Aufruf:  powershell -ExecutionPolicy Bypass -File install.ps1  [-SkipSheetSage] [-SkipModels]
param([switch]$SkipSheetSage, [switch]$SkipModels)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Cu128 = "https://download.pytorch.org/whl/cu128"
$YuETag = "yue2-v0.1.6"

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Need($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "$cmd nicht gefunden. $hint" }
}
# Native Tools schreiben Fortschritt nach stderr; massgeblich ist nur der Exit-Code.
function Run {
    $ErrorActionPreference = "Continue"
    & $args[0] $args[1..($args.Length - 1)]
    if ($LASTEXITCODE -ne 0) { throw "Fehlgeschlagen: $args" }
}

Step "Voraussetzungen pruefen"
Need uv "Installieren: winget install astral-sh.uv"
Need ffmpeg "Installieren: winget install Gyan.FFmpeg"
Need git "Installieren: winget install Git.Git"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { Write-Warning "Ollama nicht gefunden - https://ollama.com" }

# ---------------------------------------------------------------- YuE2 + App (Python 3.12)
Step "YuE2-Umgebung (.venv-yue2, Python 3.12)"
if (-not (Test-Path .venv-yue2)) { Run uv venv .venv-yue2 --python 3.12 }
$Py = ".venv-yue2\Scripts\python.exe"
# Zuerst CUDA-12.8-Torch (Blackwell/sm_120), dann YuE2 - dessen Pin torch==2.10.0 ist damit erfuellt.
Run uv pip install --python $Py "torch==2.10.0" --index-url $Cu128
Run uv pip install --python $Py "yue2-infer @ git+https://github.com/multimodal-art-projection/YuE.git@$YuETag"
Run uv pip install --python $Py -r requirements-app.txt
Run $Py -c "import torch; assert torch.cuda.is_available(), 'CUDA nicht verfuegbar'; print('Torch', torch.__version__, torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))"

# ---------------------------------------------------------------- SheetSage2 (Python 3.11)
if (-not $SkipSheetSage) {
    Step "SheetSage2-Umgebung (.venv-sheetsage2, Python 3.11) fuer Remakes"
    if (-not (Test-Path .venv-sheetsage2)) { Run uv venv .venv-sheetsage2 --python 3.11 }
    $SPy = ".venv-sheetsage2\Scripts\python.exe"
    Run uv pip install --python $SPy "torch==2.8.0" "torchaudio==2.8.0" --index-url $Cu128
    Run uv pip install --python $SPy "huggingface-hub==0.36.0"
    if (-not (Test-Path models\SheetSage2\config.json)) {
        Run $SPy -c "from huggingface_hub import snapshot_download; snapshot_download('m-a-p/SheetSage2', local_dir='models/SheetSage2')"
    }
    Run uv pip install --python $SPy -r models\SheetSage2\requirements.txt soundfile hf_xet
    Run $SPy -c "import torch; print('SheetSage2-Torch', torch.__version__, torch.cuda.is_available())"
}

# ---------------------------------------------------------------- Modelle vorab laden
if (-not $SkipModels) {
    Step "Modelle herunterladen (YuE2-3B, YuE2-Vae, Whisper) - das dauert beim ersten Mal"
    Run $Py -c "from yue2.storage import resolve_model; print(resolve_model('m-a-p/YuE2-3B')); print(resolve_model('m-a-p/YuE2-Vae'))"
    Run $Py -c "from huggingface_hub import snapshot_download; snapshot_download('openai/whisper-large-v3-turbo', allow_patterns=['*.json','*.safetensors','*.txt'])"
}

Step "YuE2-Selbsttest"
& .venv-yue2\Scripts\yue2.exe doctor
Write-Host "`nFertig. Start mit: start.bat" -ForegroundColor Green
