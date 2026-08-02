; npmpi installer - Inno Setup script
;
; Builds a self-extracting npmpi-setup.exe that installs dist\npmpi.exe
; into %LOCALAPPDATA%\npmpi, adds that folder to the current user's PATH,
; and registers a normal Add/Remove Programs uninstaller. No admin rights
; needed (installs per-user, same footprint as install.ps1) - PrivilegesRequired
; is set to lowest so it won't trigger a UAC prompt.
;
; It does NOT touch ~/.npmpi/config.json or ~/.npmpi/credentials.dat, on
; install or uninstall - those live outside {app} and are managed entirely
; by `npmpi setup`.
;
; Requires Inno Setup 6 (https://jrsoftware.org/isinfo.php) to compile.
; Build dist\npmpi.exe FIRST (via build_exe.ps1), then either:
;
;   iscc npmpi_installer.iss
;   iscc /DMyAppVersion=0.1.6 npmpi_installer.iss   (bake in a version number)
;
; ...or just run build_installer.ps1, which does both steps for you.
; Output: installer_output\npmpi-setup.exe

#define MyAppName "NPMPI"
#define MyAppPublisher "Travis Sylvester"
#define MyAppExeName "npmpi.exe"
#define MyAppURL "https://github.com/tjsyl/NPMPI"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif

[Setup]
AppId={{A079625E-6708-4C61-AA36-C63226600A27}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\npmpi
DisableProgramGroupPage=yes
DisableWelcomePage=no
DisableDirPage=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer_output
OutputBaseFilename=npmpi-setup
Compression=lzma2
SolidCompression=yes
SetupLogging=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\npmpi.exe"; DestDir: "{app}"; Flags: ignoreversion

[Code]
const
  EnvironmentKey = 'Environment';

// Append {app} to the current user's PATH, unless it's already in there.
// This is the standard Inno Setup community pattern for editing PATH.
procedure EnvAddPath(Path: string);
var
  Paths: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths) then
    Paths := '';

  if Pos(';' + Uppercase(Path) + ';', ';' + Uppercase(Paths) + ';') > 0 then
    exit;

  Paths := Paths + ';' + Path + ';';

  if RegWriteStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths) then
    Log(Format('Added [%s] to user PATH', [Path]))
  else
    Log(Format('Failed to add [%s] to user PATH', [Path]));
end;

// Remove {app} from the current user's PATH on uninstall.
procedure EnvRemovePath(Path: string);
var
  Paths: string;
  P: Integer;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths) then
    exit;

  P := Pos(';' + Uppercase(Path) + ';', ';' + Uppercase(Paths) + ';');
  if P = 0 then
    exit;

  // P is a 1-based position within the ';'-prefixed search string, so the
  // matching position in the real (unprefixed) Paths string is P - 1.
  Delete(Paths, P - 1, Length(Path) + 1);

  if RegWriteStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths) then
    Log(Format('Removed [%s] from user PATH', [Path]))
  else
    Log(Format('Failed to remove [%s] from user PATH', [Path]));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    EnvAddPath(ExpandConstant('{app}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    EnvRemovePath(ExpandConstant('{app}'));
end;

procedure InitializeWizard();
begin
  WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 +
    'npmpi has been added to your PATH. Open a NEW Command Prompt or ' +
    'PowerShell window (existing ones won''t see the change) and run:' + #13#10#13#10 +
    '    npmpi setup' + #13#10#13#10 +
    'to get started.';
end;
