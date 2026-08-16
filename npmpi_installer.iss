; npmpi installer - Inno Setup script
;
; Builds a self-extracting npmpi-setup.exe that installs both npmpi.exe
; (CLI) and npmpigui.exe (always opens straight to the GUI - two separate
; exes because a single one can't reliably tell double-click apart from
; terminal launch, see gui_main.py/commands/gui.py for why) into
; %LOCALAPPDATA%\npmpi, adds a Start Menu shortcut (+ optional desktop
; shortcut) for the GUI exe, and registers a normal Add/Remove Programs
; uninstaller. No admin rights needed (installs per-user, same footprint
; as install.ps1) - PrivilegesRequired is set to lowest so it won't
; trigger a UAC prompt.
;
; Both exes are --onedir PyInstaller builds (an exe alongside its
; dependency files, not a single packed file - --onefile made npmpigui.exe
; take 10+ seconds to open every time since it had to self-extract first).
; Each one lands in its OWN subfolder under {app} (npmpi\ and npmpigui\)
; rather than both flattened into {app} directly - they each ship their
; own "_internal" support-file folder, and merging two different onedir
; trees into one flat directory would make those collide. {app}\npmpi is
; what goes on PATH, not {app} itself.
;
; It does NOT touch ~/.npmpi/config.json or ~/.npmpi/credentials.dat, on
; install or uninstall - those live outside {app} and are managed entirely
; by `npmpi setup`.
;
; Requires Inno Setup 6 (https://jrsoftware.org/isinfo.php) to compile.
; Build dist\npmpi\ + dist\npmpigui\ FIRST (via build_exe.ps1), then either:
;
;   iscc npmpi_installer.iss
;   iscc /DMyAppVersion=0.1.6 npmpi_installer.iss   (bake in a version number)
;
; ...or just run build_installer.ps1, which does both steps for you.
; Output: installer_output\npmpi-setup.exe

#define MyAppName "NPMPI"
#define MyAppPublisher "Travis Sylvester"
#define MyAppExeName "npmpi\npmpi.exe"
#define MyAppGuiExeName "npmpigui\npmpigui.exe"
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
SetupIconFile=src\npmpi\gui\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\npmpi\*"; DestDir: "{app}\npmpi"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\npmpigui\*"; DestDir: "{app}\npmpigui"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut for the npmpi GUI"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Icons]
Name: "{group}\NpmPi"; Filename: "{app}\{#MyAppGuiExeName}"; Comment: "Open the npmpi GUI"
Name: "{userdesktop}\NpmPi"; Filename: "{app}\{#MyAppGuiExeName}"; Tasks: desktopicon; Comment: "Open the npmpi GUI"

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
  // {app}\npmpi, not {app} itself - that's the subfolder npmpi.exe
  // actually lives in (see the top-of-file comment on the onedir layout).
  if CurStep = ssPostInstall then
    EnvAddPath(ExpandConstant('{app}\npmpi'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    EnvRemovePath(ExpandConstant('{app}\npmpi'));
end;

procedure InitializeWizard();
begin
  WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 +
    'npmpi has been added to your PATH. Open a NEW Command Prompt or ' +
    'PowerShell window (existing ones won''t see the change) and run:' + #13#10#13#10 +
    '    npmpi setup' + #13#10#13#10 +
    'to get started - or use the npmpi shortcut in your Start Menu ' +
    '(or on your desktop, if you checked that box) to open the GUI ' +
    'directly.';
end;
