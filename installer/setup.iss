; OBS Remote — Inno Setup installer script
; https://jrsoftware.org/isinfo.php
;
; To build: iscc setup.iss
; Expects the PyInstaller output in ..\dist\OBSRemote\

#define MyAppName "OBS Remote"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Jessomadic"
#define MyAppURL "https://github.com/Jessomadic/OBS_Remote"
#define MyAppExeName "OBSRemote.exe"
#define MyServiceName "OBSRemote"
#define DistDir "..\dist\OBSRemote"

[Setup]
AppId={{B8D9F3A2-1C4E-4F7B-9A0D-6E2C8F5A3B1D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\OBSRemote
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Compression
Compression=lzma2/ultra64
SolidCompression=yes
; Require admin for service registration
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
; Output
OutputDir=..\dist
OutputBaseFilename=OBSRemote_Setup_{#MyAppVersion}
; Uninstall
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
; Misc
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no
; Architecture
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startupicon"; Description: "Start OBS Remote tray icon when Windows starts"; GroupDescription: "Startup:"; Flags: checkedonce

[Files]
; All PyInstaller output files
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: not startupicon

[Registry]
; Add to startup for tray icon if task selected
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "OBSRemote"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startupicon

[Run]
; Stop existing service if upgrading
Filename: "sc.exe"; Parameters: "stop {#MyServiceName}"; Flags: runhidden waituntilterminated; Check: ServiceExists
Filename: "sc.exe"; Parameters: "delete {#MyServiceName}"; Flags: runhidden waituntilterminated; Check: ServiceExists

; Install and start Windows service
Filename: "{app}\{#MyAppExeName}"; Parameters: "install"; Flags: runhidden waituntilterminated; Description: "Installing Windows service"
Filename: "sc.exe"; Parameters: "start {#MyServiceName}"; Flags: runhidden waituntilterminated; Description: "Starting service"

; Add Windows Firewall rule so browsers on the local network can reach the web UI
Filename: "netsh.exe"; Parameters: "advfirewall firewall delete rule name=""OBS Remote"""; Flags: runhidden waituntilterminated
Filename: "netsh.exe"; Parameters: "advfirewall firewall add rule name=""OBS Remote"" dir=in action=allow program=""{app}\{#MyAppExeName}"" enable=yes profile=private,domain"; Flags: runhidden waituntilterminated; Description: "Adding firewall rule"

; Launch tray icon now (for new installs with startup task selected)
Filename: "{app}\{#MyAppExeName}"; Description: "Launch OBS Remote tray icon"; Flags: nowait postinstall skipifsilent; Tasks: startupicon

[UninstallRun]
; Stop and remove service on uninstall
Filename: "sc.exe"; Parameters: "stop {#MyServiceName}"; Flags: runhidden waituntilterminated; RunOnceId: "StopService"
Filename: "sc.exe"; Parameters: "delete {#MyServiceName}"; Flags: runhidden waituntilterminated; RunOnceId: "DeleteService"
; Kill tray icon
Filename: "taskkill.exe"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden waituntilterminated; RunOnceId: "KillTray"
; Remove firewall rule
Filename: "netsh.exe"; Parameters: "advfirewall firewall delete rule name=""OBS Remote"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveFirewall"

[Code]
function ServiceExists: Boolean;
var
  ResultCode: Integer;
begin
  Exec('sc.exe', 'query {#MyServiceName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := (ResultCode = 0);
end;
