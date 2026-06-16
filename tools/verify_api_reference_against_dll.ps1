<#
.SYNOPSIS
  Validate docs/api_reference.json arg counts against the AUTHORITATIVE
  SOLIDWORKS interop type libraries (api\redist\*.dll).

.DESCRIPTION
  docs/api_reference.md is generated from the decompiled CHM *help* files.
  The CHM is documentation; the interop DLLs are the actual COM metadata for
  this SW build. This script reflects over the DLLs (metadata only -- it does
  NOT launch SOLIDWORKS or instantiate any COM object) and asserts that every
  method's arg count in the reference matches the DLL. COM properties surface
  in .NET interop as get_/set_ accessors, so those are matched separately and
  reported as OK rather than "absent".

  Exit code 0 = every method matches (or is a known property); 1 = mismatch(es).

.PARAMETER Redist
  Path to the SOLIDWORKS api\redist folder. Defaults to the standard install.

.PARAMETER RefJson
  Path to docs/api_reference.json. Defaults relative to this script.

.EXAMPLE
  powershell -File tools/verify_api_reference_against_dll.ps1
#>
param(
  [string]$Redist = "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist",
  [string]$RefJson = (Join-Path $PSScriptRoot "..\docs\api_reference.json")
)

$ErrorActionPreference = "Stop"

$sldDll = Join-Path $Redist "SolidWorks.Interop.sldworks.dll"
$constDll = Join-Path $Redist "SolidWorks.Interop.swconst.dll"
if (-not (Test-Path $sldDll)) {
  Write-Host "SKIP: interop DLL not found at $sldDll (no local SW install?)" -ForegroundColor Yellow
  exit 0
}

$null = [Reflection.Assembly]::LoadFrom($constDll)
$sld = [Reflection.Assembly]::LoadFrom($sldDll)

# Index interface methods and property-accessor param counts.
$methods = @{}     # "Iface.Method" -> HashSet[int] of param counts
$props   = @{}     # "Iface.Prop"   -> HashSet[int] of indexer param counts (from getter)
foreach ($t in ($sld.GetExportedTypes() | Where-Object { $_.IsInterface })) {
  foreach ($m in $t.GetMethods()) {
    $name = $m.Name
    if ($name -like 'get_*' -or $name -like 'set_*') {
      $key = "{0}.{1}" -f $t.Name, $name.Substring(4)
      if (-not $props.ContainsKey($key)) { $props[$key] = New-Object 'System.Collections.Generic.HashSet[int]' }
      $null = $props[$key].Add($m.GetParameters().Count)
    } else {
      $key = "{0}.{1}" -f $t.Name, $name
      if (-not $methods.ContainsKey($key)) { $methods[$key] = New-Object 'System.Collections.Generic.HashSet[int]' }
      $null = $methods[$key].Add($m.GetParameters().Count)
    }
  }
}

$ref = ([System.IO.File]::ReadAllText($RefJson)) | ConvertFrom-Json
$total = 0; $ok = 0; $asProp = 0
$mismatch = @(); $absent = @()
foreach ($p in $ref.methods.PSObject.Properties) {
  $total++
  $fq = $p.Name; $argc = [int]$p.Value.args_count
  if ($methods.ContainsKey($fq)) {
    if ($methods[$fq].Contains($argc)) { $ok++ }
    else { $mismatch += [pscustomobject]@{ Method = $fq; Reference = $argc; DLL = (($methods[$fq] | Sort-Object) -join "/") } }
  } elseif ($props.ContainsKey($fq)) {
    $asProp++   # COM property accessed method-style in pywin32; not an arg-count concern
  } else {
    $absent += $fq
  }
}

Write-Host ("methods checked        : {0}" -f $total)
Write-Host ("arg-count OK vs DLL    : {0}" -f $ok) -ForegroundColor Green
Write-Host ("COM properties (skip)  : {0}" -f $asProp)
Write-Host ("ABSENT in DLL          : {0}" -f $absent.Count)
Write-Host ("MISMATCHES             : {0}" -f $mismatch.Count) -ForegroundColor ($(if ($mismatch.Count) { "Red" } else { "Green" }))

if ($absent.Count) {
  Write-Host "`nABSENT in DLL (method in reference, not in interop):" -ForegroundColor Yellow
  $absent | Sort-Object | ForEach-Object { Write-Host "  $_" }
}
if ($mismatch.Count) {
  Write-Host "`nMISMATCHES (reference arg count != DLL overload set):" -ForegroundColor Red
  ($mismatch | Sort-Object Method | Format-Table -AutoSize | Out-String -Width 200).Trim() | Write-Host
  exit 1
}
if ($absent.Count) { exit 1 }
Write-Host "`nOK: every reference method matches the DLL." -ForegroundColor Green
exit 0
