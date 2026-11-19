; Help Guide Publisher Windows installer. Source is ASCII for Windows PowerShell-era tooling.
#define AppName "Help Guide Publisher"
#define AppVersion "1.1.0"
#define AppPublisher "Matthew Cannizzaro"
#define AppExeName "Help Guide Publisher.exe"

[Setup]
AppId={{BFD0B73F-C97A-44D2-9CE1-273A4D5C77E6}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Help Guide Publisher
DefaultGroupName=Help Guide Publisher
OutputDir=..\installer-output
OutputBaseFilename=HelpGuidePublisherSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExeName}
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\dist\Help Guide Publisher\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Icons]
Name: "{autoprograms}\Help Guide Publisher"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\Help Guide Publisher"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch Help Guide Publisher"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
  if not IsWin64 then begin
    MsgBox('Help Guide Publisher requires 64-bit Windows 10 or later.', mbError, MB_OK);
    Result := False;
  end;
end;
