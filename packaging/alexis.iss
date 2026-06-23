; Inno Setup script for the ALEXIS desktop app.
; Build the exe first (packaging\build.ps1), then compile this with Inno Setup 6.1+:
;     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\alexis.iss
; Produces: packaging\Output\ALEXIS-Setup.exe
;
; Installs per-user (no admin needed), adds Start Menu + optional desktop
; shortcut, and bootstraps the Edge WebView2 runtime if it is missing
; (pywebview needs it to render the window).

#define AppName "ALEXIS"
#define AppVersion "0.1.0"
#define AppPublisher "IQVIA Laboratories"
#define AppExe "ALEXIS.exe"
; Folder produced by PyInstaller (packaging\build.ps1 writes here):
#define DistDir "C:\ALEXIS_build\dist\ALEXIS"

[Setup]
AppId={{B6F1E2A4-7C3D-4E9A-9F12-ALEXIS000001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=ALEXIS-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
function WebView2Installed(): Boolean;
var
  v: String;
begin
  { Evergreen runtime GUID; present under HKLM (per-machine) or HKCU (per-user). }
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v) or
    RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v);
  if Result then
    Result := (v <> '') and (v <> '0.0.0.0');
end;

procedure InstallWebView2();
var
  tmp: String;
  rc: Integer;
begin
  if WebView2Installed() then
    exit;
  tmp := ExpandConstant('{tmp}\MicrosoftEdgeWebView2Setup.exe');
  try
    DownloadTemporaryFile('https://go.microsoft.com/fwlink/p/?LinkId=2124703',
                          'MicrosoftEdgeWebView2Setup.exe', '', nil);
    { DownloadTemporaryFile saves into {tmp} using the supplied name. }
    if Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebView2Setup.exe'),
            '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, rc) then
      Log('WebView2 bootstrapper exit code: ' + IntToStr(rc))
    else
      Log('Failed to launch WebView2 bootstrapper.');
  except
    MsgBox('Could not install the Edge WebView2 runtime automatically. ' +
           'If ALEXIS shows a blank window, install it from ' +
           'https://developer.microsoft.com/microsoft-edge/webview2/',
           mbInformation, MB_OK);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    InstallWebView2();
end;
