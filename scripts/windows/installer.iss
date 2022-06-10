[Setup]
AppId={{B31ABF4F-C8FF-417E-87DB-265888D72165}
AppName={APP_DISP_NAME}
AppVersion={APP_VERSION}
AppVerName={APP_NAME}
AppPublisher={APP_AUTHOR}
AppPublisherURL={APP_URL}
WizardStyle=classic
DefaultDirName={autopf}\{APP_NAME}
DefaultGroupName={APP_DISP_NAME}
UninstallDisplayIcon={app}\{APP_NAME}.exe
Compression=lzma2
LZMAUseSeparateProcess=yes
SolidCompression=yes
ShowLanguageDialog=no
VersionInfoVersion={APP_VERSION}
VersionInfoCompany={APP_AUTHOR}
VersionInfoCopyright=(c) 2021 {APP_AUTHOR}
VersionInfoProductName={APP_DISP_NAME}
VersionInfoProductVersion={APP_VERSION}
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
SourceDir={APP_SRC}
ChangesAssociations=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "*"; DestDir: "{app}"; Flags: recursesubdirs;

[Icons]
Name: "{group}\{APP_DISP_NAME}"; Filename: "{app}\{APP_NAME}.exe"
Name: "{group}\{cm:UninstallProgram,{APP_NAME}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{APP_DISP_NAME}"; Filename: "{app}\{APP_NAME}.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{APP_NAME}.exe"; Flags: nowait postinstall skipifsilent 64bit; Description: "{cm:LaunchProgram,{APP_NAME}}"

[Registry]
{APP_FILE_ASSOCIATIONS}
Root: HKCR; SubKey: "Local Settings\Software\Microsoft\Windows\Shell\MuiCache"; ValueType: string; ValueName: "{app}\{APP_NAME}.exe.FriendlyAppName"; ValueData: "{APP_DISP_NAME}"; Flags: uninsdeletevalue
Root: HKCR; SubKey: "Local Settings\Software\Microsoft\Windows\Shell\MuiCache"; ValueType: string; ValueName: "{app}\{APP_NAME}.exe.ApplicationCompany"; ValueData: "{APP_AUTHOR}"; Flags: uninsdeletevalue
