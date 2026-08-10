param(
    [string]$ProjectRoot = "C:\Users\phs03\ai_feedback_mvp"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ProjectRoot)) {
    Write-Error "Project root not found: $ProjectRoot"
    exit 1
}

$patterns = @(
    "OSAD",
    "osad",
    "OSAD_Report",
    "osad_report"
)

$extensions = @(
    ".py",
    ".jsx",
    ".js",
    ".tsx",
    ".ts",
    ".css",
    ".html",
    ".json",
    ".md",
    ".env"
)

$excludeDirs = @(
    ".git",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv"
)

$files = Get-ChildItem -Path $ProjectRoot -Recurse -File |
    Where-Object {
        $extensions -contains $_.Extension.ToLower() -and
        -not ($excludeDirs | ForEach-Object {
            $_dir = $_
            $_.FullName -match [regex]::Escape("\$_dir\")
        } | Where-Object { $_ } | Select-Object -First 1)
    }

$results = @()

foreach ($file in $files) {
    foreach ($pattern in $patterns) {
        $matches = Select-String `
            -Path $file.FullName `
            -Pattern $pattern `
            -SimpleMatch `
            -CaseSensitive:$false

        foreach ($match in $matches) {
            $results += [PSCustomObject]@{
                File = $file.FullName.Replace($ProjectRoot + "\", "")
                Line = $match.LineNumber
                Pattern = $pattern
                Text = $match.Line.Trim()
            }
        }
    }
}

$results = $results |
    Sort-Object File, Line, Pattern |
    Select-Object -Unique File, Line, Pattern, Text

Write-Host ""
Write-Host "=== OSAD residual audit ===" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host "Matches: $($results.Count)"
Write-Host ""

if ($results.Count -eq 0) {
    Write-Host "No OSAD residual strings found." -ForegroundColor Green
} else {
    $results | Format-Table -AutoSize -Wrap
}

$outputCsv = Join-Path $ProjectRoot "osad_residual_audit.csv"
$results | Export-Csv `
    -Path $outputCsv `
    -NoTypeInformation `
    -Encoding UTF8

Write-Host ""
Write-Host "CSV saved to:" -ForegroundColor Yellow
Write-Host $outputCsv
