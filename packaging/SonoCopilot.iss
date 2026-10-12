#ifndef BuildDir
  #define BuildDir "..\dist\SonoCopilot"
#endif
#ifndef ReleaseDir
  #define ReleaseDir "..\release"
#endif

[Setup]
AppId={{7D88F907-7342-4867-9DC9-EB5D93E6C504}
AppName=SonoCopilot VLM
AppVersion=1.0.0
AppPublisher=SonoCopilot
AppPublisherURL=https://github.com/Turubayev/SonoCopilot-VLM
AppSupportURL=https://github.com/Turubayev/SonoCopilot-VLM/issues
AppUpdatesURL=https://github.com/Turubayev/SonoCopilot-VLM/releases
DefaultDirName={localappdata}\Programs\SonoCopilot
DefaultGroupName=SonoCopilot VLM
UninstallDisplayIcon={app}\SonoCopilot.exe
UninstallDisplayName=SonoCopilot VLM
OutputDir={#ReleaseDir}
OutputBaseFilename=SonoCopilot-Setup-1.0.0
SetupIconFile=sonocopilot.ico
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19045
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
CreateUninstallRegKey=not IsTestInstall

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"; Flags: unchecked

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SonoCopilot VLM"; Filename: "{app}\SonoCopilot.exe"; WorkingDir: "{app}"; Check: not IsTestInstall
Name: "{autodesktop}\SonoCopilot VLM"; Filename: "{app}\SonoCopilot.exe"; WorkingDir: "{app}"; Tasks: desktopicon; Check: not IsTestInstall

[Run]
Filename: "{app}\SonoCopilot.exe"; Description: "Запустить SonoCopilot VLM"; Flags: nowait postinstall skipifsilent; Check: not IsTestInstall

[Code]
function IsTestInstall: Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/TESTINSTALL') = 0 then
      Result := True;
end;
