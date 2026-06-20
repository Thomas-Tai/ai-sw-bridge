# Route-C in-process probe harness (W67 Track-2)

A reusable **in-process diagnostic vehicle** for classifying out-of-process
SOLIDWORKS walls: does a feature ghost because of the **COM marshaling
boundary**, or because the **Parasolid solver structurally refuses** it?

Run any walled feature's exact call from inside SOLIDWORKS' own process (a
direct `ISldWorks` pointer, no marshaling) and compare the geometric effect to
the OOP attempt. Same ghost in-process ⇒ kernel wall. Materializes in-process ⇒
COM-boundary wall.

## Why an add-in (and not RunMacro2)

`ISldWorks.RunMacro2(dll, module, proc, …)` on a raw-`csc`-compiled class
library returns `NoError` but **silently never executes the method** — the VSTA
host only runs genuine VSTA-IDE-scaffolded assemblies (proven: a file sentinel
written as `Main`'s first line never appears, across instance/static entry
shapes and cache-defeating unique DLL names). `.swp` is a binary VBA project,
not text-authorable. So the only headless, text-authorable, truly-in-process
vehicle is a **COM add-in implementing `ISwAddin`**.

## Files

- `RouteCAddin.cs` — the `ISwAddin` add-in. `ConnectToSW` casts `ThisSW` to a
  direct `ISldWorks` and runs the payload in-process, writing a sentinel to
  `%TEMP%\route_c_sentinel.txt`. **Swap the body of `RunPayload` to probe a
  different walled feature.**
- `RouteCThicken.cs` — the earlier RunMacro2 payload (kept as the forensic
  record that RunMacro2 + a hand-compiled DLL no-ops).
- `build_route_c.ps1` — compiles `RouteCThicken.cs` to a uniquely-named DLL
  (RunMacro2 cache-defeat). The add-in is built with the command below.
- `../spike_route_c_thicken.py` — the RunMacro2 orchestrator (forensic record).

## Build (headless, .NET Framework csc — NOT the dotnet SDK)

The VSTA/add-in host is the .NET Framework CLR, so target Framework `csc`:

```powershell
$csc    = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$redist = "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist"
& $csc /nologo /target:library /out:RouteCAddin.dll `
  "/reference:$redist\SolidWorks.Interop.sldworks.dll" `
  "/reference:$redist\SolidWorks.Interop.swconst.dll" `
  "/reference:$redist\SolidWorks.Interop.swpublished.dll" RouteCAddin.cs
```

`ISwAddin` lives in `SolidWorks.Interop.swpublished` (not `sldworks`). `regasm`
must be able to LOAD the DLL to invoke `ComRegisterFunction`, so the three
`SolidWorks.Interop.*.dll` must sit next to it (copy them in; they are
git-ignored — licensed SW redist, do not commit).

## Deploy (ELEVATED — one-time)

`regasm` writes HKLM (HKCR COM keys) + HKLM `SOLIDWORKS\Addins` + HKCU
`AddInsStartup`, which needs admin:

```powershell
# from an Administrator PowerShell, OR self-elevate from a normal shell:
$regasm = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe"
$dll    = "<...>\spikes\v0_2x\route_c\RouteCAddin.dll"
Start-Process -FilePath $regasm -ArgumentList "`"$dll`"","/codebase" -Verb RunAs -Wait
```

Verify (HKLM reads need no admin):

```powershell
$g = "{C0FFEE00-1234-4567-89AB-FEEDFACE0001}"
Test-Path "HKLM:\SOFTWARE\SOLIDWORKS\Addins\$g"      # add-in discovery
Test-Path "HKLM:\SOFTWARE\Classes\CLSID\$g"          # COM class
Test-Path "HKCU:\Software\SOLIDWORKS\AddInsStartup\$g" # per-user enable
```

## Iterate (no re-register — GUID/path are fixed)

SW **locks** the DLL while loaded, so rebuild only while SW is closed:

```
1. taskkill /IM SLDWORKS.exe /F          # release the DLL lock
2. rm %TEMP%\route_c_sentinel.txt         # clear stale result
3. <rebuild RouteCAddin.dll in place>     # same GUID/path -> no re-register
4. start sldworks.exe                      # ConnectToSW fires the payload
5. poll %TEMP%\route_c_sentinel.txt        # read the in-process telemetry
```

`Start-Process` needs `-WorkingDirectory` set to a bracket-free path (the repo
path contains `[Local]`, which PowerShell treats as a wildcard).

## Teardown (ELEVATED — leave the seat clean)

```powershell
$regasm = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe"
$dll    = "<...>\spikes\v0_2x\route_c\RouteCAddin.dll"
Start-Process -FilePath $regasm -ArgumentList "`"$dll`"","/unregister" -Verb RunAs -Wait
# then confirm the three keys above are gone and relaunch SW to confirm no load.
```

## W67 Track-2 result (FeatureBossThicken)

In-process, direct `ISldWorks` pointer, valid standalone planar surface, sheet
body selected (`SELCOUNT=1`), full flag matrix `direction{0,1,2} ×
FillVolume{F,T} × Merge{F,T}` = **12/12 ghosted** (`ret:null, dsolids:0,
dvol:0.0000`). Identical to OOP ⇒ **kernel wall, not COM boundary**. The W66
thicken DEFER is proven, not assumed. See
`../_results/route_c_sweep_sentinel.txt`.
