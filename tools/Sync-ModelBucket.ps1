param(
    [switch]$Apply
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot ".runtime"))
$registryPath = Join-Path $projectRoot "config\model_mirror_registry.json"
$registry = Get-Content -LiteralPath $registryPath -Raw | ConvertFrom-Json
$bucketUri = [string]$registry.destination.uri

if (-not (Get-Command hf -ErrorAction SilentlyContinue)) {
    throw "The Hugging Face CLI is required. Install or expose the 'hf' command before syncing."
}

foreach ($model in $registry.models | Where-Object { $_.mirror_enabled }) {
    $localPath = [IO.Path]::GetFullPath((Join-Path $projectRoot ([string]$model.local_dir)))
    if (-not $localPath.StartsWith($runtimeRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to sync a model path outside the project runtime directory: $localPath"
    }
    if (-not (Test-Path -LiteralPath $localPath -PathType Container)) {
        throw "Configured model directory is missing: $localPath"
    }

    $destination = "$bucketUri/$($model.bucket_path)"
    $command = @(
        "sync",
        $localPath,
        $destination,
        "--exclude=.cache/**",
        "--exclude=.locks/**",
        "--exclude=**/__pycache__/**"
    )
    if (-not $Apply) {
        Write-Host ("DRY RUN: hf " + ($command -join " "))
        continue
    }

    Write-Host ("Syncing " + $model.id + " to " + $destination)
    & hf @command
    if ($LASTEXITCODE -ne 0) {
        throw "Model sync failed for $($model.id) with exit code $LASTEXITCODE"
    }
}
