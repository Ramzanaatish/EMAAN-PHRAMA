; Inno Setup script — Pharma Purchase Assistant (Windows installer)
; Build the app first (see run_instruction.md), then compile this file
; with Inno Setup 6 to produce PharmaPurchaseAssistant-Setup.exe.

#define AppName "Pharma Purchase Assistant"
#define AppVersion "1.3.4"
#define AppPublisher "EMAN PHARMACY & VACCINE"
#define AppExeName "PharmaPurchaseAssistant.exe"

[Setup]
AppId={{8F3A2C1E-4B7A-4E2D-9C5F-1A2B3C4D5E6F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Pharma Purchase Assistant
DefaultGroupName=Pharma Purchase Assistant
DisableProgramGroupPage=yes
OutputDir=..\installer-output
OutputBaseFilename=PharmaPurchaseAssistant-Setup-1.3.4
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
; The app only reads the local SQL Server instance (localhost\SQLEXPRESS)
; and keeps its own SQLite database under %LOCALAPPDATA%.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\PharmaPurchaseAssistant\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\PharmaPurchaseAssistant\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
