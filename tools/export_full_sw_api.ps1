<#
.SYNOPSIS
  Export the FULL SOLIDWORKS API surface from EVERY interop type library in
  api\redist (every interface, method, property, enum), labelled with the
  license/key availability constraint per assembly, for dev-time lookup.

.DESCRIPTION
  Reflects over ALL api\redist\SolidWorks.Interop.*.dll assemblies (metadata
  only -- does NOT launch SOLIDWORKS or instantiate COM). Each interface/enum
  is tagged with its source `assembly` and an `access` tier:

    core   - usable with any SOLIDWORKS license; just needs SW running
    key    - needs a SEPARATE license key (Document Manager); runs without SW
    addin  - needs that add-in/product to be licensed + loaded

  Each assembly also gets `installed` = a LIVE registry probe of this machine
  (registered / not-detected). IMPORTANT: the registry proves install/
  registration, NOT license entitlement -- confirm actual entitlement at runtime
  (running SOLIDWORKS via ISldWorks, or the SolidNetWork License manager). The
  Document Manager key is a developer-held string, not in the registry.

.PARAMETER Redist  api\redist folder. Defaults to the standard install path.
.PARAMETER OutDir  Output dir for sw_api_full.json/.md. Defaults to ../docs.
.EXAMPLE  powershell -File tools/export_full_sw_api.ps1
#>
param(
  [string]$Redist = "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist",
  [string]$OutDir = (Join-Path $PSScriptRoot "..\docs")
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $Redist)) { Write-Host "ERROR: $Redist not found"; exit 2 }

$null = [Reflection.Assembly]::LoadFrom((Join-Path $Redist "SolidWorks.Interop.swconst.dll"))
$sld  = [Reflection.Assembly]::LoadFrom((Join-Path $Redist "SolidWorks.Interop.sldworks.dll"))
$buildVer = $sld.GetName().Version.ToString()

function Short([string]$n) { ($n -replace '^SolidWorks\.Interop\.', '') -replace '\.dll$', '' }
function Clean-Type([Type]$t) { $x=$t.Name; if($x.EndsWith('&')){$x=$x.Substring(0,$x.Length-1)}; return $x }
function Esc([string]$s) {
  if ($null -eq $s) { return "" }
  $s = $s.Replace('\','\\').Replace('"','\"').Replace("`r",'').Replace("`n",' ').Replace("`t",' '); return $s
}

# ---- availability model (curated tiers + product names) ----
$ACCESS = @{
  'sldworks'                 = @{p='SOLIDWORKS core application API'; a='core';  n='Any SOLIDWORKS license; needs SW running'}
  'swconst'                  = @{p='SOLIDWORKS constants / enums';    a='core';  n='Constants only'}
  'swcommands'               = @{p='SOLIDWORKS command IDs';          a='core';  n='swCommands_e for RunCommand'}
  'swpublished'              = @{p='SOLIDWORKS published-reference API';a='core'; n='Part of core'}
  'swdimxpert'               = @{p='DimXpert';                         a='core';  n='DimXpert is core; MBD publish may need SOLIDWORKS MBD'}
  'sustainability'           = @{p='SOLIDWORKS Sustainability';        a='core';  n='Included with SOLIDWORKS'}
  'sw3dprinter'              = @{p='Print3D';                          a='core';  n='Core print API'}
  'swdocumentmgr'            = @{p='SOLIDWORKS Document Manager';      a='key';   n='Needs a Document Manager license KEY (separate, from the SOLIDWORKS API portal); runs WITHOUT SOLIDWORKS'}
  'cosworks'                 = @{p='SOLIDWORKS Simulation';           a='addin'; n='Needs Simulation license + add-in loaded'}
  'swmotionstudy'            = @{p='SOLIDWORKS Motion';               a='addin'; n='Motion Analysis needs SOLIDWORKS Motion (Premium); Basic Motion is core'}
  'sldcostingapi'            = @{p='SOLIDWORKS Costing';              a='addin'; n='Costing (Professional+)'}
  'SWRoutingLib'             = @{p='SOLIDWORKS Routing';              a='addin'; n='Routing (Premium) add-in'}
  'dsgnchk'                  = @{p='SOLIDWORKS Design Checker';       a='addin'; n='Design Checker (Professional+)'}
  'gtswutilities'            = @{p='SOLIDWORKS Utilities';            a='addin'; n='Utilities (Professional+)'}
  'fworks'                   = @{p='FeatureWorks';                    a='addin'; n='FeatureWorks recognition (Premium)'}
  'swbrowser'                = @{p='SOLIDWORKS Toolbox Browser';      a='addin'; n='Toolbox (Professional+)'}
  'sldtoolboxconfigureaddin' = @{p='SOLIDWORKS Toolbox (configure)';  a='addin'; n='Toolbox (Professional+)'}
}
# registry evidence paths per assembly (any-exists => registered on THIS machine)
$REG = @{
  'cosworks'      = @('HKLM:\SOFTWARE\SOLIDWORKS\SOLIDWORKS 2024\Applications\SOLIDWORKS Simulation','HKCU:\SOFTWARE\SOLIDWORKS\SOLIDWORKS 2024\Simulation')
  'swmotionstudy' = @('HKLM:\SOFTWARE\SOLIDWORKS\SOLIDWORKS 2024\Applications\SOLIDWORKS Motion')
  'SWRoutingLib'  = @('HKLM:\SOFTWARE\SOLIDWORKS\Applications\SOLIDWORKS Routing','HKLM:\SOFTWARE\SOLIDWORKS\SOLIDWORKS 2024\Routing')
  'sldcostingapi' = @('HKLM:\SOFTWARE\SOLIDWORKS\SOLIDWORKS 2024\Applications\SOLIDWORKS Costing','HKCU:\SOFTWARE\SOLIDWORKS\SOLIDWORKS 2024\Costing')
  'dsgnchk'       = @('HKCU:\SOFTWARE\SOLIDWORKS\SOLIDWORKS 2024\DesignCheck')
  'gtswutilities' = @('HKLM:\SOFTWARE\SOLIDWORKS\Applications\SOLIDWORKS Utilities')
  'fworks'        = @('HKLM:\SOFTWARE\SOLIDWORKS\Applications\FeatureWorks')
  'swbrowser'     = @('HKLM:\SOFTWARE\SOLIDWORKS\Applications\SOLIDWORKS Toolbox Browser','HKLM:\SOFTWARE\SOLIDWORKS\Applications\SOLIDWORKS Toolbox')
  'sldtoolboxconfigureaddin' = @('HKLM:\SOFTWARE\SOLIDWORKS\Applications\SOLIDWORKS Toolbox')
  'sustainability'= @('HKLM:\SOFTWARE\SOLIDWORKS\SOLIDWORKS 2024\Applications\SOLIDWORKS Sustainability')
}
function Avail([string]$short) {
  $m = $ACCESS[$short]
  if (-not $m) { $m = @{p=$short; a='unknown'; n=''} }
  $installed = 'n/a'
  if ($m.a -eq 'core') { $installed = 'core (always)' }
  elseif ($m.a -eq 'key') { $installed = 'interop present; key held by developer' }
  else {
    $installed = 'not-detected'
    if ($REG.ContainsKey($short)) { foreach ($rp in $REG[$short]) { if (Test-Path $rp) { $installed = 'registered'; break } } }
  }
  return [pscustomobject]@{ product=$m.p; access=$m.a; note=$m.n; installed=$installed }
}

# ---- load every interop assembly ----
$dlls = Get-ChildItem $Redist -Filter "SolidWorks.Interop.*.dll" | Sort-Object Name
$asmRecords = @(); $skippedAsm = @()
foreach ($d in $dlls) {
  try { $asm=[Reflection.Assembly]::LoadFrom($d.FullName); $types=$asm.GetExportedTypes() }
  catch { $skippedAsm += (Short $d.Name); continue }
  $ifaces = $types | Where-Object {
    $_.IsInterface -and ($_.GetProperties().Count -gt 0 -or (($_.GetMethods()|?{$_.Name -notlike 'get_*' -and $_.Name -notlike 'set_*'}).Count -gt 0))
  } | Sort-Object Name
  $enums = $types | Where-Object { $_.IsEnum } | Sort-Object Name
  if ($ifaces.Count -eq 0 -and $enums.Count -eq 0) { continue }
  $sh = Short $d.Name
  $asmRecords += [pscustomobject]@{ Short=$sh; Ifaces=$ifaces; Enums=$enums; Av=(Avail $sh) }
}
$asmRecords = $asmRecords | Sort-Object Short

$jb = New-Object System.Text.StringBuilder
$mb = New-Object System.Text.StringBuilder
$totIf=0;$totMethod=0;$totProp=0;$totEnum=0;$totMember=0

# ---- MD header + availability legend + per-assembly table ----
[void]$mb.AppendLine("# SOLIDWORKS API - Full Reference (all interop assemblies)")
[void]$mb.AppendLine("")
[void]$mb.AppendLine("Generated from EVERY ``api\redist\SolidWorks.Interop.*.dll`` (metadata only - does not launch SOLIDWORKS).")
[void]$mb.AppendLine("Core interop version **$buildVer**. Each interface/enum is tagged with its source ``assembly`` and ``access`` tier.")
[void]$mb.AppendLine("")
[void]$mb.AppendLine("**Access tiers:** ``core`` = any SOLIDWORKS license, needs SW running - ``key`` = separate Document Manager license key, runs without SW - ``addin`` = needs that product licensed + loaded.")
[void]$mb.AppendLine("")
[void]$mb.AppendLine("> **Constraint caveat:** ``installed`` is a LIVE registry probe of THIS machine and proves install/registration, NOT license entitlement. Confirm actual entitlement at runtime (running SOLIDWORKS, or the SolidNetWork License manager). The Document Manager key is held by the developer, not in the registry.")
[void]$mb.AppendLine("")
[void]$mb.AppendLine("> The small curated subset the bridge actually wraps (with arg docs) lives in ``docs/api_reference.md``.")
[void]$mb.AppendLine("")
[void]$mb.AppendLine("## Assemblies")
[void]$mb.AppendLine("")
[void]$mb.AppendLine("| Assembly | Product | Access | Installed (this machine) | Interfaces | Enums |")
[void]$mb.AppendLine("|----------|---------|--------|--------------------------|-----------:|------:|")
foreach ($a in $asmRecords) {
  [void]$mb.AppendLine(("| ``{0}`` | {1} | ``{2}`` | {3} | {4} | {5} |" -f $a.Short, $a.Av.product, $a.Av.access, $a.Av.installed, $a.Ifaces.Count, $a.Enums.Count))
}
if ($skippedAsm.Count) { [void]$mb.AppendLine(""); [void]$mb.AppendLine(("> Skipped (load failed): {0}" -f ($skippedAsm -join ", "))) }
[void]$mb.AppendLine("")

# ---- JSON header (rich assemblies array) ----
[void]$jb.Append('{')
[void]$jb.Append(('"build":"{0}","source":"interop:redist (all assemblies)","access_legend":{{"core":"any SOLIDWORKS license; needs SW running","key":"separate Document Manager license key; runs without SW","addin":"needs that product licensed + loaded"}},"installed_caveat":"registry probe = install/registration only, NOT license entitlement","assemblies":[' -f $buildVer))
$fa=$true
foreach ($a in $asmRecords) {
  if(-not $fa){[void]$jb.Append(',')}; $fa=$false
  [void]$jb.Append(('{{"name":"{0}","product":"{1}","access":"{2}","note":"{3}","installed":"{4}","interface_count":{5},"enum_count":{6}}}' -f (Esc $a.Short),(Esc $a.Av.product),(Esc $a.Av.access),(Esc $a.Av.note),(Esc $a.Av.installed),$a.Ifaces.Count,$a.Enums.Count))
}
[void]$jb.Append('],"interfaces":[')

# ---- interfaces ----
$firstI=$true
foreach ($a in $asmRecords) {
  if ($a.Ifaces.Count) { [void]$mb.AppendLine(("## Interfaces - ``{0}``  (access: ``{1}`` - {2}; installed: {3})" -f $a.Short,$a.Av.access,$a.Av.product,$a.Av.installed)); [void]$mb.AppendLine("") }
  foreach ($t in $a.Ifaces) {
    $realMethods=$t.GetMethods()|?{$_.Name -notlike 'get_*' -and $_.Name -notlike 'set_*'}|Sort-Object Name,{$_.GetParameters().Count}
    $propInfos=$t.GetProperties()|Sort-Object Name
    $totIf++;$totMethod+=$realMethods.Count;$totProp+=$propInfos.Count
    if(-not $firstI){[void]$jb.Append(',')}; $firstI=$false
    [void]$jb.Append(('{{"assembly":"{0}","access":"{1}","name":"{2}","methods":[' -f (Esc $a.Short),(Esc $a.Av.access),(Esc $t.Name)))
    [void]$mb.AppendLine(("### {0}  *({1} methods, {2} properties)*" -f $t.Name,$realMethods.Count,$propInfos.Count))
    [void]$mb.AppendLine("")
    $firstM=$true
    foreach ($m in $realMethods) {
      $ps=$m.GetParameters();$sig=@();$jp=@()
      foreach ($pp in $ps) {
        $pt=Clean-Type $pp.ParameterType;$dir="";if($pp.IsOut){$dir="out "}elseif($pp.ParameterType.IsByRef){$dir="ref "}
        $sig+=("{0}{1} {2}" -f $dir,$pt,$pp.Name)
        $jp+=('{{"name":"{0}","type":"{1}","dir":"{2}"}}' -f (Esc $pp.Name),(Esc $pt),$dir.Trim())
      }
      $ret=Clean-Type $m.ReturnType
      [void]$mb.AppendLine(("- ``{0}({1}) -> {2}``" -f $m.Name,($sig -join ", "),$ret))
      if(-not $firstM){[void]$jb.Append(',')}; $firstM=$false
      [void]$jb.Append(('{{"name":"{0}","returns":"{1}","args":{2},"params":[{3}]}}' -f (Esc $m.Name),(Esc $ret),$ps.Count,($jp -join ',')))
    }
    [void]$jb.Append('],"properties":[')
    if($propInfos.Count){[void]$mb.AppendLine("")}
    $firstP=$true
    foreach ($pi in $propInfos) {
      $pt=Clean-Type $pi.PropertyType;$idx=$pi.GetIndexParameters()
      $idxStr=if($idx.Count){"["+(($idx|%{(Clean-Type $_.ParameterType)+" "+$_.Name}) -join ", ")+"]"}else{""}
      [void]$mb.AppendLine(("- *prop* ``{0}{1} : {2}``" -f $pi.Name,$idxStr,$pt))
      if(-not $firstP){[void]$jb.Append(',')}; $firstP=$false
      [void]$jb.Append(('{{"name":"{0}","type":"{1}","index_args":{2}}}' -f (Esc $pi.Name),(Esc $pt),$idx.Count))
    }
    [void]$jb.Append(']}')
    [void]$mb.AppendLine("")
  }
}

# ---- enums ----
[void]$jb.Append('],"enums":[')
$firstE=$true
foreach ($a in $asmRecords) {
  if ($a.Enums.Count) { [void]$mb.AppendLine(("## Enums - ``{0}``  (access: ``{1}``)" -f $a.Short,$a.Av.access)); [void]$mb.AppendLine("") }
  foreach ($e in $a.Enums) {
    $pairs=@(); foreach($nm in [Enum]::GetNames($e)){ $pairs+=[pscustomobject]@{Name=$nm;Value=[int][Enum]::Parse($e,$nm)} }
    $pairs=$pairs|Sort-Object Value,Name
    $totEnum++;$totMember+=$pairs.Count
    if(-not $firstE){[void]$jb.Append(',')}; $firstE=$false
    $jm=($pairs|%{'{{"name":"{0}","value":{1}}}' -f (Esc $_.Name),$_.Value}) -join ','
    [void]$jb.Append(('{{"assembly":"{0}","access":"{1}","name":"{2}","members":[{3}]}}' -f (Esc $a.Short),(Esc $a.Av.access),(Esc $e.Name),$jm))
    [void]$mb.AppendLine(("### {0}" -f $e.Name)); [void]$mb.AppendLine("")
    [void]$mb.AppendLine("| Member | Value |"); [void]$mb.AppendLine("|--------|-------|")
    foreach ($pr in $pairs) { [void]$mb.AppendLine(("| ``{0}`` | {1} |" -f $pr.Name,$pr.Value)) }
    [void]$mb.AppendLine("")
  }
}
[void]$jb.Append(']}')

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }
$jsonPath = Join-Path $OutDir "sw_api_full.json"
$mdPath   = Join-Path $OutDir "sw_api_full.md"
[System.IO.File]::WriteAllText($jsonPath, $jb.ToString(), (New-Object System.Text.UTF8Encoding($false)))
[System.IO.File]::WriteAllText($mdPath,   $mb.ToString(), (New-Object System.Text.UTF8Encoding($false)))

"core build version : $buildVer"
"assemblies         : {0}" -f $asmRecords.Count
"interfaces         : {0}" -f $totIf
"methods            : {0}" -f $totMethod
"properties         : {0}" -f $totProp
"enums              : {0}  (members: {1})" -f $totEnum,$totMember
""
"availability label per assembly:"
foreach ($a in $asmRecords) { "  {0,-26} access={1,-7} installed={2}" -f $a.Short,$a.Av.access,$a.Av.installed }
$jlen=(Get-Item -LiteralPath $jsonPath).Length; $mlen=(Get-Item -LiteralPath $mdPath).Length
""
"wrote JSON         : $jsonPath  ({0:N2} MB)" -f ($jlen/1MB)
"wrote MD           : $mdPath  ({0:N2} MB)" -f ($mlen/1MB)
