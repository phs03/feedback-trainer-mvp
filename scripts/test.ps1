param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

Write-Host "==== AI Feedback MVP Smoke Test ===="
Write-Host "Base URL: $BaseUrl"
Write-Host ""

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Method,
        [string]$Path,
        $Body = $null
    )

    $url = "$BaseUrl$Path"
    Write-Host "[$Name] $Method $url"

    try {
        if ($Method -eq "GET") {
            $res = Invoke-RestMethod -Method GET -Uri $url
        }
        elseif ($Method -eq "POST") {
            $json = $Body | ConvertTo-Json -Depth 5
            $res = Invoke-RestMethod -Method POST -Uri $url -Body $json -ContentType "application/json"
        }
        else {
            throw "Unsupported method: $Method"
        }

        Write-Host "  OK"
        $res | Format-List | Out-String -Stream | Select-Object -First 5 | ForEach-Object {
            Write-Host "    $_"
        }
    }
    catch {
        Write-Host "  ERROR: $($_.Exception.Message)"
    }

    Write-Host ""
}

# 1) health endpoints
Test-Endpoint -Name "Health"  -Method "GET" -Path "/health"
Test-Endpoint -Name "Healthz" -Method "GET" -Path "/healthz"
Test-Endpoint -Name "Readyz"  -Method "GET" -Path "/readyz"

# 2) /feedback sample body (very simple, ASCII only)
$feedbackBody = @{
    encounter_id = "SMOKE-TEST-001"
    supervisor_id = "SUP-001"
    trainee_id    = "TRN-001"
    audio_ref     = $null
    transcript    = "This is a simple feedback message for smoke testing."
}

Test-Endpoint -Name "Feedback" -Method "POST" -Path "/feedback" -Body $feedbackBody

Write-Host "==== Smoke Test Finished ===="
