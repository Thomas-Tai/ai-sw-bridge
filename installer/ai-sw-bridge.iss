; ai-sw-bridge unsigned installer (Phase 5B). Per-user, no UAC.
; Version is injected by the build script: ISCC /DAppVersion=<version>
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "ai-sw-bridge"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=ai-sw-bridge
DefaultDirName={localappdata}\Programs\ai-sw-bridge
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=ai-sw-bridge-setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ChangesEnvironment=yes
WizardStyle=modern
UninstallDisplayName={#AppName} {#AppVersion}

[Files]
Source: "runtime\*"; DestDir: "{app}\runtime"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "wheelhouse\*"; DestDir: "{app}\wheelhouse"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "README-first.txt"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Tasks]
Name: "registermcp"; Description: "Register the MCP server with Claude Desktop (ai-sw-doctor --register)"

[Run]
Filename: "{app}\runtime\python.exe"; \
  Parameters: "-m pip install --no-index --find-links ""{app}\wheelhouse"" ai_sw_bridge[mcp]"; \
  StatusMsg: "Installing ai-sw-bridge into its private Python..."; \
  Flags: runhidden waituntilterminated
Filename: "{app}\runtime\python.exe"; \
  Parameters: """{app}\runtime\Scripts\pywin32_postinstall.py"" -install"; \
  StatusMsg: "Registering COM support (pywin32)..."; \
  Flags: runhidden waituntilterminated
Filename: "{app}\runtime\Scripts\ai-sw-doctor.exe"; \
  Parameters: "--register"; Tasks: registermcp; \
  StatusMsg: "Registering MCP server with Claude Desktop..."; \
  Flags: runhidden waituntilterminated

[Code]
const
  EnvKey = 'Environment';

function ScriptsDir(): string;
begin
  Result := ExpandConstant('{app}\runtime\Scripts');
end;

function NeedsAddPath(): Boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKCU, EnvKey, 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(ScriptsDir()) + ';',
                ';' + Uppercase(OrigPath) + ';') = 0;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  OrigPath: string;
begin
  if CurStep = ssPostInstall then
  begin
    if NeedsAddPath() then
    begin
      if not RegQueryStringValue(HKCU, EnvKey, 'Path', OrigPath) then
        OrigPath := '';
      if (OrigPath <> '') and (OrigPath[Length(OrigPath)] <> ';') then
        OrigPath := OrigPath + ';';
      RegWriteExpandStringValue(HKCU, EnvKey, 'Path', OrigPath + ScriptsDir());
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  OrigPath, Needle: string;
  P: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if RegQueryStringValue(HKCU, EnvKey, 'Path', OrigPath) then
    begin
      Needle := ScriptsDir();
      P := Pos(Uppercase(Needle), Uppercase(OrigPath));
      if P > 0 then
      begin
        Delete(OrigPath, P, Length(Needle));
        StringChangeEx(OrigPath, ';;', ';', True);
        if (Length(OrigPath) > 0) and (OrigPath[Length(OrigPath)] = ';') then
          Delete(OrigPath, Length(OrigPath), 1);
        RegWriteExpandStringValue(HKCU, EnvKey, 'Path', OrigPath);
      end;
    end;
  end;
end;
