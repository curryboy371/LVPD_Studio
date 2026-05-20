# PowerShell에서 lvpd.bat 실행 (창이 바로 닫히는 문제 방지)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
if ($args.Count -eq 0) {
    cmd.exe /k "lvpd.bat"
} else {
    $cmd = 'lvpd.bat ' + ($args -join ' ')
    cmd.exe /c "$cmd & pause"
}
exit $LASTEXITCODE
