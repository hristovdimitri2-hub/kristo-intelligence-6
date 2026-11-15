param([switch]$Execute)

$ErrorActionPreference = 'Stop'
$Repo      = 'C:\Users\AlienWare\Desktop\projects\kristo-intelligence-6'
$Log       = Join-Path $Repo 'data\phase1_micro_payments.log'
$PlanJson  = Join-Path $Repo 'data\phase1_micro_payments_plan.json'
$Helper    = Join-Path $Repo 'scripts\phase1_paid_call.py'
$TaskName  = 'KristoPhase1MicroPayments'
$Base      = 'https://kristo-intelligence-api.onrender.com'
$Rpc       = 'https://mainnet.base.org'
$Usdc      = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
$PayerRe   = '0xE50c5212[0-9a-fA-F]{27}35763'   # PUBLIC demo payer address pattern (never a key)
$Pad24     = '000000000000000000000000'
$CapUsd    = 0.10
$MaxCalls  = 21
$MaxDays   = 7

function Log([string]$m) {
  $l = "{0:yyyy-MM-dd HH:mm:ss} | {1}" -f (Get-Date), $m
  Add-Content -Path $Log -Value $l -Encoding UTF8
  Write-Host $l
}

function Get-EthWei([string]$addr) {
  $body = '{"jsonrpc":"2.0","id":1,"method":"eth_getBalance","params":["' + $addr + '","latest"]}'
  $r = Invoke-RestMethod -Uri $Rpc -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 20
  $hex = ($r.result -replace '^0x','')
  if ($hex -eq '') { $hex = '0' }
  $wei = [System.Numerics.BigInteger]::Parse($hex, [System.Globalization.NumberStyles]::HexNumber)
  return [double]$wei / 1e18
}

function Get-UsdcBalance([string]$addr) {
  $data = '0x70a08231' + $Pad24 + ($addr -replace '^0x','')
  $body = '{"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":"' + $Usdc + '","data":"' + $data + '"},"latest"]}'
  $r = Invoke-RestMethod -Uri $Rpc -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 20
  $hex = ($r.result -replace '^0x','')
  if ($hex -eq '' -or $hex -eq '0') { return 0 }
  $raw = [System.Numerics.BigInteger]::Parse($hex, [System.Globalization.NumberStyles]::HexNumber)
  return [double]$raw / 1e6
}

function Get-PayerAddress {
  $dirs = @("$Repo\docs","$Repo\data","$Repo\scripts","$Repo\_tools","$Repo\tests") | Where-Object { Test-Path $_ }
  $rx = New-Object System.Text.RegularExpressions.Regex($PayerRe,
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
  foreach ($d in $dirs) {
    $files = Get-ChildItem -Path $d -Recurse -File -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -notmatch '\\secrets\\' -and $_.Length -lt 1MB -and
                     $_.Extension -notin @('.db','.sqlite','.png','.jpg','.pdf','.woff') }
    foreach ($f in $files) {
      try { $txt = [IO.File]::ReadAllText($f.FullName) } catch { continue }
      $m = $rx.Match($txt)
      if ($m.Success) { Log ("PAYER address found in: " + $f.FullName); return $m.Value }
    }
  }
  return $null
}

function Get-Quote([string]$path) {
  try {
    $resp = Invoke-WebRequest -Uri ($Base + $path) -Method Get -UseBasicParsing `
             -Headers @{ Accept = 'application/json' } -TimeoutSec 40
    return @{ Status = [int]$resp.StatusCode; Body = [string]$resp.Content }
  } catch {
    $resp = $_.Exception.Response
    if ($null -ne $resp) {
      $sr = New-Object IO.StreamReader($resp.GetResponseStream())
      $txt = $sr.ReadToEnd(); $sr.Close()
      return @{ Status = [int]$resp.StatusCode; Body = $txt }
    }
    return @{ Status = 0; Body = $_.Exception.Message }
  }
}

function Get-AmountUsd([string]$body) {
  $m = [regex]::Match($body, '"(?:maxAmountRequired|amount)"\s*:\s*"?([0-9.]+)"?')
  if (-not $m.Success) { return -1 }
  $v = 0.0
  $okParse = [double]::TryParse($m.Groups[1].Value,
               [System.Globalization.NumberStyles]::Float,
               [System.Globalization.CultureInfo]::InvariantCulture, [ref]$v)
  if (-not $okParse) { return -1 }
  if ($v -ge 1) { $v = $v / 1e6 }          # value came in base units (6 decimals)
  if ($v -lt 0.000001) { return -1 }
  return $v
}

function Show-PublicMailEnv {
  $p = Join-Path $Repo '.env'
  if (-not (Test-Path $p)) { Log '.env not present'; return }
  Get-Content $p | ForEach-Object {
    if ($_ -match '^(SMTP_HOST|SMTP_PORT|SMTP_USER|MAIL_RECIPIENT)=') { Log ("ENV-PUBLIC: " + $_) }
  }
}

function Invoke-Preflight {
  Log '===== PREFLIGHT (read-only: no payments, no keys) ====='
  Show-PublicMailEnv
  $fail = @()

  if (-not (Test-Path $Helper)) { $fail += 'scripts\phase1_paid_call.py is missing' }

  $payer = Get-PayerAddress
  if (-not $payer) {
    $fail += 'demo payer PUBLIC address not found outside secrets\'
  } else {
    Log ("PAYER = " + $payer)
    try {
      $eth  = Get-EthWei $payer
      $usdc = Get-UsdcBalance $payer
      Log ("PAYER BALANCE: USDC=" + $usdc + "  ETH=" + $eth)
      if ($usdc -lt $CapUsd) { $fail += ("payer USDC " + $usdc + " is below cap " + $CapUsd) }
    } catch { $fail += ("Base RPC check failed: " + $_.Exception.Message) }
  }

  $qS = Get-Quote '/api/v1/signal'
  $qW = Get-Quote '/api/v1/whaleflow'
  $pS = -1; $pW = -1
  foreach ($pair in @(@('/api/v1/signal', $qS), @('/api/v1/whaleflow', $qW))) {
    $path = $pair[0]; $q = $pair[1]
    Log ("QUOTE " + $path + " -> HTTP " + $q.Status)
    if ($q.Status -ne 402) { $fail += ($path + " expected HTTP 402, got " + $q.Status); continue }
    $dump = $q.Body
    if ($null -eq $dump) { $dump = '' }
    Log ("QUOTE BODY: " + $dump.Substring(0, [Math]::Min(500, $dump.Length)))
    $amt = Get-AmountUsd $dump
    if ($amt -lt 0) {
      $fail += ($path + ' price could not be parsed from 402 body')
    } else {
      if ($path -eq '/api/v1/signal') { $pS = $amt } else { $pW = $amt }
      Log ("QUOTE PRICE " + $path + " = $" + $amt)
    }
  }

  if ($pS -gt 0 -and $pW -gt 0) {
    $projected = (14 * $pS) + (7 * $pW)
    Log ("PROJECTED TOTAL (14 signal + 7 whaleflow) = $" + [math]::Round($projected, 4))
    if ($projected -gt $CapUsd) { $fail += ("projected $" + $projected + " exceeds cap $" + $CapUsd) }
    if (Test-Path $PlanJson) {
      $existing = Get-Content $PlanJson -Raw | ConvertFrom-Json
      $existing.priceSignal = $pS
      $existing.priceWhale  = $pW
      $existing | ConvertTo-Json | Set-Content -Path $PlanJson -Encoding UTF8
      Log 'PLAN refreshed with current prices (resume mode).'
    } else {
      $plan = [ordered]@{
        created     = (Get-Date).ToString('yyyy-MM-dd')
        priceSignal = $pS
        priceWhale  = $pW
        callsDone   = 0
        spentUsd    = 0
        daysRun     = ''
      }
      $plan | ConvertTo-Json | Set-Content -Path $PlanJson -Encoding UTF8
      Log 'PLAN file created.'
    }
  }

  if ($fail.Count -gt 0) {
    foreach ($f in $fail) { Log ("FAIL: " + $f) }
    Log 'PREFLIGHT FAILED -> exit, ZERO payments.'
    return $false
  }
  Log 'PREFLIGHT OK.'
  return $true
}

# ------------------------------- MAIN ---------------------------------------
$ok = Invoke-Preflight
if (-not $ok) { exit 1 }

if (-not $Execute) {
  Log 'SAFE MODE DONE. Nothing was paid.'
  Log 'Day 1 payments were approved ($0.10 cap): re-run with -Execute.'
  exit 0
}

# ------------------- EXECUTE (both doors recorded in chat) ------------------
$plan = Get-Content $PlanJson -Raw | ConvertFrom-Json
$today = (Get-Date).ToString('yyyy-MM-dd')
$days = @()
if ($plan.daysRun) { $days = @($plan.daysRun -split ',' | Where-Object { $_ -ne '' }) }
if ($days -notcontains $today) { $days += $today }
$plan.daysRun = ($days -join ',')
Log ("DAY " + $days.Count + "/" + $MaxDays + " | calls " + $plan.callsDone + "/" + $MaxCalls +
     " | spent $" + $plan.spentUsd)

$remaining = $MaxCalls - [int]$plan.callsDone
$targets = @()
if ($remaining -ge 1) { $targets += '/api/v1/signal' }
if ($remaining -ge 2) { $targets += '/api/v1/signal' }
if ($remaining -ge 3) { $targets += '/api/v1/whaleflow' }

for ($i = 0; $i -lt $targets.Count; $i++) {
  $path  = $targets[$i]
  $price = if ($path -eq '/api/v1/signal') { [double]$plan.priceSignal } else { [double]$plan.priceWhale }
  if (($plan.spentUsd + $price) -gt $CapUsd) { Log 'CAP would be exceeded -> stopping run.'; break }
  Log ("PAY " + $path + " ($" + $price + ") ...")
  $raw = ''
  try {
    $raw = ((& python $Helper --base $Base --path $path) | Select-Object -Last 1) -join ''
  } catch {
    Log ("  helper crashed: " + $_.Exception.Message); break
  }
  Log ("  helper -> " + $raw)
  $j = $null
  try { $j = ConvertFrom-Json -InputObject ($raw | Out-String) } catch { $j = $null }
  if ($j -and $j.ok) {
    $plan.callsDone = [int]$plan.callsDone + 1
    $plan.spentUsd  = [math]::Round([double]$plan.spentUsd + $price, 4)
    Log ("  OK tx=" + $j.tx + " | calls=" + $plan.callsDone + " | spent=$" + $plan.spentUsd)
  } else {
    Log '  NOT OK -> aborting todays run (failed calls cost nothing).'
    break
  }
  if ($i -lt ($targets.Count - 1)) { Start-Sleep -Seconds (Get-Random -Min 25 -Max 90) }
}

$plan.daysRun = ($days -join ',')
$plan | ConvertTo-Json | Set-Content -Path $PlanJson -Encoding UTF8

$minPrice = [Math]::Min([double]$plan.priceSignal, [double]$plan.priceWhale)
$done = ([int]$plan.callsDone -ge $MaxCalls) -or ($days.Count -ge $MaxDays) -or
        (($plan.spentUsd + $minPrice) -gt $CapUsd)
if ($done) {
  Log ('CAMPAIGN COMPLETE: calls=' + $plan.callsDone + ' spent=$' + $plan.spentUsd +
       ' days=' + $days.Count + ' -> unregistering scheduled task.')
  & schtasks.exe /Delete /TN $TaskName /F 2>$null | Out-Null
} else {
  $tr = 'powershell -NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -Execute'
  & schtasks.exe /Create /TN $TaskName /TR $tr /SC DAILY /ST 09:00 /F | Out-Null
  Log ('Daily task registered for 09:00. Remove anytime: schtasks /Delete /TN ' + $TaskName + ' /F')
}
Log 'DONE.'
