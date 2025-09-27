# PowerShell script to setup environment for different configurations

param(
    [string]$Env = "local"
)

Write-Host "🔧 Setting up environment: $Env" -ForegroundColor Cyan

# Copy the appropriate environment file
$envFile = "env.$Env.example"
if (Test-Path $envFile) {
    Copy-Item $envFile ".env"
    Write-Host "✅ Copied $envFile to .env" -ForegroundColor Green
} else {
    Write-Host "❌ Environment file $envFile not found" -ForegroundColor Red
    Write-Host "Available environments:" -ForegroundColor Yellow
    Get-ChildItem "env.*.example" | ForEach-Object { Write-Host "  $($_.Name)" }
    exit 1
}

# Load environment variables from .env file
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -and !$_.StartsWith("#")) {
            $parts = $_.Split("=", 2)
            if ($parts.Length -eq 2) {
                [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
            }
        }
    }
}

Write-Host "🔧 Environment variables loaded:" -ForegroundColor Cyan
Write-Host "  ENVIRONMENT: $($env:ENVIRONMENT)" -ForegroundColor White
Write-Host "  DB_HOST: $($env:DB_HOST)" -ForegroundColor White
Write-Host "  DB_USER: $($env:DB_USER)" -ForegroundColor White
Write-Host "  GITHUB_USER: $($env:GITHUB_USER)" -ForegroundColor White
Write-Host "  GITHUB_BRANCH: $($env:GITHUB_BRANCH)" -ForegroundColor White

Write-Host ""
Write-Host "🚀 Ready to run generator with $Env environment" -ForegroundColor Green
Write-Host "Run: python generate_site.py" -ForegroundColor Yellow
