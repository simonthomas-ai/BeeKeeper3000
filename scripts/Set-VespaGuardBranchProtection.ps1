[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$Owner = "simonthomas-ai"
)

$ErrorActionPreference = "Stop"

function Invoke-GitHubJson {
    param([Parameter(Mandatory)][string[]]$GhArguments)

    $output = & gh @GhArguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        $message = ($output | ForEach-Object { "$_" }) -join " "
        throw "GitHub CLI request failed: $message"
    }

    $jsonText = ($output | ForEach-Object { "$_" }) -join [Environment]::NewLine
    if ([string]::IsNullOrWhiteSpace($jsonText)) {
        return $null
    }
    return $jsonText | ConvertFrom-Json
}

function Get-ExistingProtection {
    param([Parameter(Mandatory)][string]$Repository)

    $endpoint = "repos/$Repository/branches/main/protection"
    $output = & gh api $endpoint 2>&1
    $exitCode = $LASTEXITCODE
    $message = ($output | ForEach-Object { "$_" }) -join " "

    if ($exitCode -eq 0) {
        return ($message | ConvertFrom-Json)
    }
    if ($message -match 'HTTP 404|Branch not protected|Not Found') {
        return $null
    }

    throw "Cannot safely read current branch protection for $Repository. No change made. $message"
}

$policies = @(
    @{
        Repository = "$Owner/BeeKeeper3000"
        RequiredChecks = @(
            "Python core and safety tests",
            "Camera runtime safety tests",
            "Windows camera runtime compatibility tests",
            "Monitor bridge tests",
            "Analyze source (python)",
            "Analyze source (javascript-typescript)"
        )
    },
    @{
        Repository = "$Owner/Beekeeper-Monitor"
        RequiredChecks = @(
            "gesamttest",
            "BeeKeeper3000 $([char]0x2013) Bridge-Integration"
        )
    }
)

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI 'gh' is not installed. Install it from https://cli.github.com/ and sign in with 'gh auth login'."
}

& gh auth status
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is not authenticated. Run 'gh auth login' and retry."
}

$plans = @()
foreach ($policy in $policies) {
    $repository = $policy.Repository
    $metadata = Invoke-GitHubJson -GhArguments @("api", "repos/$repository")
    if (-not $metadata.permissions.admin) {
        throw "The authenticated account has no confirmed admin permission for $repository. No changes have been applied."
    }

    $existing = Get-ExistingProtection -Repository $repository
    if ($null -ne $existing) {
        throw "Existing branch protection is already configured for $repository. No repository was changed. This helper refuses to overwrite or weaken an existing policy; add the required status checks manually while preserving the existing rules."
    }

    $contexts = @($policy.RequiredChecks) |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Sort-Object -Unique

    $payload = [ordered]@{
        required_status_checks = [ordered]@{
            strict = $true
            contexts = @($contexts)
        }
        enforce_admins = $true
        required_pull_request_reviews = [ordered]@{
            dismiss_stale_reviews = $true
            require_code_owner_reviews = $false
            required_approving_review_count = 0
            require_last_push_approval = $false
        }
        restrictions = $null
        required_linear_history = $true
        allow_force_pushes = $false
        allow_deletions = $false
        required_conversation_resolution = $true
    }

    $plans += [pscustomobject]@{
        Repository = $repository
        Endpoint = "repos/$repository/branches/main/protection"
        RequiredChecks = $contexts
        Payload = $payload
    }
}

Write-Host ""
Write-Host "Branch-protection plan for both repositories:" -ForegroundColor Cyan
foreach ($plan in $plans) {
    Write-Host ""
    Write-Host "  $($plan.Repository)" -ForegroundColor Yellow
    foreach ($check in $plan.RequiredChecks) {
        Write-Host "    REQUIRED: $check"
    }
    Write-Host "    Require pull requests: yes (0 approvals required; suitable for a single-maintainer repository)"
    Write-Host "    Require branch up to date: yes"
    Write-Host "    Enforce for administrators: yes"
    Write-Host "    Force-push / branch deletion: blocked"
    Write-Host "    Conversation resolution / linear history: required"
}

if (-not $Apply) {
    Write-Host ""
    Write-Host "DRY RUN ONLY. No repository settings were changed." -ForegroundColor Green
    Write-Host "Review the checks above, then rerun with -Apply to write and verify both protections."
    return
}

foreach ($plan in $plans) {
    $temporaryFile = New-TemporaryFile
    try {
        $json = $plan.Payload | ConvertTo-Json -Depth 12
        [System.IO.File]::WriteAllText(
            $temporaryFile.FullName,
            $json,
            [System.Text.UTF8Encoding]::new($false)
        )

        $null = Invoke-GitHubJson -GhArguments @(
            "api",
            "--method", "PUT",
            "--header", "X-GitHub-Api-Version: 2026-03-10",
            $plan.Endpoint,
            "--input", $temporaryFile.FullName
        )
    }
    finally {
        Remove-Item -LiteralPath $temporaryFile.FullName -Force -ErrorAction SilentlyContinue
    }

    $verified = Invoke-GitHubJson -GhArguments @(
        "api",
        "--header", "X-GitHub-Api-Version: 2026-03-10",
        $plan.Endpoint
    )

    $actualContexts = @()
    if ($verified.required_status_checks.contexts) {
        $actualContexts = @($verified.required_status_checks.contexts)
    }
    foreach ($required in $plan.RequiredChecks) {
        if ($required -notin $actualContexts) {
            throw "Verification failed for $($plan.Repository): required status check missing: $required"
        }
    }

    if (-not $verified.enforce_admins.enabled -or
        $verified.required_status_checks.strict -ne $true -or
        $verified.allow_force_pushes.enabled -ne $false -or
        $verified.allow_deletions.enabled -ne $false -or
        $verified.required_conversation_resolution.enabled -ne $true) {
        throw "Branch-protection verification failed for $($plan.Repository). Inspect Settings > Branches."
    }

    Write-Host "VERIFIED: $($plan.Repository) main is protected." -ForegroundColor Green
}

Write-Host ""
Write-Host "Both main branches are protected and their settings were read back successfully." -ForegroundColor Green
