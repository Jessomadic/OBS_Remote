; OBS Remote — Inno Setup installer script
; https://jrsoftware.org/isinfo.php
;
; To build: iscc setup.iss
; Expects the PyInstaller output in ..\dist\OBSRemote\

#define MyAppName "OBS Remote"
#define MyAppVersion "1.0.8"
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
; Always require admin — service installation and firewall rules need elevation
PrivilegesRequired=admin
; Output
OutputDir=..\dist
OutputBaseFilename=OBSRemote_Setup_{#MyAppVersion}
; Uninstall
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
; Misc
WizardStyle=modern
DisableProgramGroupPage=yes
; Do NOT use CloseApplications — it can't see Session 0 service processes.
; We kill them ourselves in CurStepChanged before file copy begins.
CloseApplications=no
RestartApplications=no
; Architecture
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startupicon"; Description: "Start OBS Remote tray icon when Windows starts"; GroupDescription: "Startup:"; Flags: checkedonce

[Dirs]
; Create the shared config/log directory with write access for all users.
; Without this, the service (SYSTEM) creates it with restrictive ACLs and
; the tray (user account) can't save config without an admin prompt.
Name: "{commonappdata}\OBSRemote"; Permissions: users-modify

[Files]
; All PyInstaller output files — copied AFTER CurStepChanged kills old process
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: not startupicon

[Registry]
; Add to startup for tray icon if task selected
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "OBSRemote"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startupicon

[Run]
; Install and start Windows service (old one already removed in CurStepChanged)
Filename: "{app}\{#MyAppExeName}"; Parameters: "install"; Flags: runhidden waituntilterminated; Description: "Installing Windows service"
; Belt-and-suspenders: ensure auto-start even if _svc_start_type_ wasn't set in older builds
Filename: "sc.exe"; Parameters: "config {#MyServiceName} start= auto"; Flags: runhidden waituntilterminated
Filename: "sc.exe"; Parameters: "start {#MyServiceName}"; Flags: runhidden waituntilterminated; Description: "Starting service"

; Add Windows Firewall rules so browsers on the local network can reach the web UI.
; Two rules for belt-and-suspenders:
;   1. Program rule — allows the exe on any profile (works even if network is "Public")
;   2. Port rule  — allows TCP 42069 inbound (reliable for services running as SYSTEM)
; Both are deleted on uninstall.
Filename: "netsh.exe"; Parameters: "advfirewall firewall delete rule name=""OBS Remote"""; Flags: runhidden waituntilterminated
Filename: "netsh.exe"; Parameters: "advfirewall firewall delete rule name=""OBS Remote Port"""; Flags: runhidden waituntilterminated
Filename: "netsh.exe"; Parameters: "advfirewall firewall add rule name=""OBS Remote"" dir=in action=allow program=""{app}\{#MyAppExeName}"" enable=yes profile=any"; Flags: runhidden waituntilterminated; Description: "Adding firewall rule (program)"
Filename: "netsh.exe"; Parameters: "advfirewall firewall add rule name=""OBS Remote Port"" dir=in action=allow protocol=TCP localport=42069 enable=yes profile=any"; Flags: runhidden waituntilterminated; Description: "Adding firewall rule (port)"

; Launch tray icon after install/update (including silent auto-updates)
Filename: "{app}\{#MyAppExeName}"; Description: "Launch OBS Remote tray icon"; Flags: nowait postinstall; Tasks: startupicon

[UninstallRun]
; Kill tray icon first so the exe is not locked
Filename: "taskkill.exe"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden waituntilterminated; RunOnceId: "KillTray"
; Stop and remove service
Filename: "sc.exe"; Parameters: "stop {#MyServiceName}"; Flags: runhidden waituntilterminated; RunOnceId: "StopService"
Filename: "powershell.exe"; Parameters: "-WindowStyle Hidden -Command ""try {{ (Get-Service '{#MyServiceName}' -EA Stop).WaitForStatus('Stopped',[TimeSpan]::FromSeconds(15)) }} catch {{}}"""; Flags: runhidden waituntilterminated; RunOnceId: "WaitStopped"
Filename: "taskkill.exe"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden waituntilterminated; RunOnceId: "KillTray2"
Filename: "sc.exe"; Parameters: "delete {#MyServiceName}"; Flags: runhidden waituntilterminated; RunOnceId: "DeleteService"
; Remove firewall rules
Filename: "netsh.exe"; Parameters: "advfirewall firewall delete rule name=""OBS Remote"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveFirewall"
Filename: "netsh.exe"; Parameters: "advfirewall firewall delete rule name=""OBS Remote Port"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveFirewallPort"

[Code]
function ServiceExists: Boolean;
var
  ResultCode: Integer;
begin
  Exec('sc.exe', 'query {#MyServiceName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := (ResultCode = 0);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
  begin
    // Kill tray icon — it holds a file lock on the exe in user session
    Exec('taskkill.exe', '/F /IM {#MyAppExeName}', '',
         SW_HIDE, ewWaitUntilTerminated, ResultCode);

    if ServiceExists() then
    begin
      // Gracefully stop the service
      Exec('sc.exe', 'stop {#MyServiceName}', '',
           SW_HIDE, ewWaitUntilTerminated, ResultCode);

      // Wait until the service process has actually exited (sc stop returns
      // before the process dies — this is the root cause of upgrade failures)
      Exec('powershell.exe',
           '-WindowStyle Hidden -Command "' +
           'try { (Get-Service ''{#MyServiceName}'' -EA Stop)' +
           '.WaitForStatus(''Stopped'',[TimeSpan]::FromSeconds(20)) } catch {}"',
           '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

      // Force-kill the process if it is still alive after graceful stop
      Exec('taskkill.exe', '/F /IM {#MyAppExeName}', '',
           SW_HIDE, ewWaitUntilTerminated, ResultCode);

      // Remove old service registration so the new exe registers cleanly
      Exec('sc.exe', 'delete {#MyServiceName}', '',
           SW_HIDE, ewWaitUntilTerminated, ResultCode);

      // Brief pause for SCM to process the deletion before files are copied
      Exec('ping.exe', '-n 3 127.0.0.1', '',
           SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
  end;
end;
