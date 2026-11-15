# ПРОВЕРКА НА КЛЮЧ ЗА payTo
#
# Пита те за private key, извежда адреса от него и казва дали това е
# адресът, който търсим.
#
# Ключът НЕ се записва на диск, НЕ се праща никъде и НЕ се показва на екрана.
#
# Стартиране: десен бутон -> "Run with PowerShell", или в терминал:
#     .\check_key.ps1

$ErrorActionPreference = 'Stop'

$targetNice = '0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f'

$py = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
$checker = Join-Path $PSScriptRoot 'check_key.py'

Write-Host ''
Write-Host '  ============================================================'
Write-Host '   ПРОВЕРКА НА КЛЮЧ ЗА payTo'
Write-Host '  ============================================================'
Write-Host ''
Write-Host '   Търсим ключа, който дава адрес:'
Write-Host "   $targetNice"
Write-Host ''
Write-Host '   Ключът е 64 знака (0-9, a-f), обикновено започва с 0x.'
Write-Host '   В MetaMask: акаунт -> трите точки -> Account details'
Write-Host '               -> Show private key'
Write-Host ''

$key = $null

# Три начина на подаване, по приоритет: конвейер, пренасочен вход, интерактивно.
$piped = @($input)
if ($piped.Count -gt 0 -and $piped[0]) {
    $key = [string]$piped[0]
} elseif ([Console]::IsInputRedirected) {
    $key = [Console]::In.ReadLine()
} else {
    $sec = Read-Host '   Постави ключа (не се вижда)'
    if ($sec) {
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
        try   { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    }
}

if (-not $key) { Write-Host '   Празно - нищо за проверка.'; exit 1 }
$key = $key.Trim()
if (-not $key) { Write-Host '   Празно - нищо за проверка.'; exit 1 }

$out = $key | & $py $checker 2>&1
$key = $null
[GC]::Collect()

$addr   = ($out | Where-Object { $_ -like 'ADDR|*' }   | Select-Object -First 1)
$result = ($out | Where-Object { $_ -like 'RESULT|*' } | Select-Object -First 1)
$bad    = ($out | Where-Object { $_ -like 'INVALID|*' -or $_ -like 'NO_LIB|*' } | Select-Object -First 1)

if ($bad) {
    Write-Host ''
    Write-Host '   Това не е валиден private key.'
    Write-Host '   Провери дали си копирал целия низ - трябва да е 64 знака.'
    Write-Host ''
    $out | ForEach-Object { Write-Host "   $_" }
    exit 1
}

if (-not $addr) {
    Write-Host ''
    Write-Host '   Не успях да проверя ключа. Ето какво върна Python:'
    $out | ForEach-Object { Write-Host "   $_" }
    exit 1
}

$address = $addr.Substring(5)

Write-Host ''
Write-Host '   Адресът на този ключ е:'
Write-Host "   $address"
Write-Host ''

if ($result -eq 'RESULT|MATCH') {
    Write-Host '   ###########################################################'
    Write-Host '   #                                                         #'
    Write-Host '   #   ТОВА Е КЛЮЧЪТ.                                        #'
    Write-Host '   #                                                         #'
    Write-Host '   ###########################################################'
    Write-Host ''
    Write-Host '   Кажи на агента, че си го намерил. НЕ го пращай в чата.'
    exit 0
}

$known = ''
if ($result -like 'RESULT|KNOWN|*') { $known = $result.Substring(13) }

$labels = @{
    'DEMO'      = 'demo портфейлът (ключът, който вече имаме)'
    'GAS'       = 'газ портфейлът (изгорен, не го финансирай)'
    'OLD_WRONG' = 'старият грешен адрес (изгорен)'
    'ANCHOR'    = 'anchor портфейлът'
}

Write-Host '   Това НЕ е ключът на payTo.'
if ($known -and $labels.ContainsKey($known)) { Write-Host "   Това е $($labels[$known])." }
Write-Host ''
Write-Host '   Известни адреси, за да разпознаваш:'
Write-Host '     demo портфейл   0xE50c5212e8211639C49276dA190E248B83935763'
Write-Host '     газ портфейл    0x9c1eb97e121a6836200C539a1BF0ecdC37F750dd'
Write-Host '     стар грешен     0xd4cdA980839C8FED4374EE37EA8DBE8c4ECfd88f'
Write-Host ''
Write-Host '   Продължавай да търсиш. Ключът е 64 знака, не е seed фраза.'
exit 2
