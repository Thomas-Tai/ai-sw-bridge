# Compile RouteCThicken.cs to a UNIQUELY-NAMED DLL (defeats VSTA assembly
# caching across RunMacro2 calls in one SOLIDWORKS session). Prints the path.
# ASCII only.
$ErrorActionPreference = "Stop"
$here = Split-Path -LiteralPath $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $here
$csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$redist = "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist"
$stamp = Get-Date -Format "MMddHHmmss"
$out = "RouteCThicken_$stamp.dll"
& $csc /nologo /target:library /out:$out "/reference:$redist\SolidWorks.Interop.sldworks.dll" "/reference:$redist\SolidWorks.Interop.swconst.dll" RouteCThicken.cs
if ($LASTEXITCODE -ne 0) { Write-Output "COMPILE_FAILED=$LASTEXITCODE"; exit 1 }
Write-Output "BUILT=$here\$out"
