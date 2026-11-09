[Setup]
AppId={{1BE5705E-9AF2-4250-8C68-E45C2DDBA6BA}
AppName={APP_DISP_NAME} mpv
AppVersion={APP_VERSION}
AppVerName={APP_NAME} mpv
AppPublisher={APP_AUTHOR}
AppPublisherURL={APP_URL}
WizardStyle=classic
DefaultDirName={autopf}\{APP_NAME} mpv
DefaultGroupName={APP_DISP_NAME} mpv
UninstallDisplayIcon={app}\{APP_NAME}.exe
Compression=lzma2
LZMAUseSeparateProcess=yes
SolidCompression=yes
ShowLanguageDialog=no
VersionInfoVersion={APP_VERSION_NUMERIC}
VersionInfoCompany={APP_AUTHOR}
VersionInfoCopyright=(c) 2021 {APP_AUTHOR}
VersionInfoProductName={APP_DISP_NAME}
VersionInfoProductVersion={APP_VERSION_NUMERIC}
VersionInfoProductTextVersion={APP_VERSION}
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
SourceDir={APP_SRC}
ChangesAssociations=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "*"; DestDir: "{app}"; Flags: recursesubdirs;

[Icons]
Name: "{group}\{APP_DISP_NAME} mpv"; Filename: "{app}\{APP_NAME}.exe"; AppUserModelID: "{APP_ID}"
Name: "{group}\{cm:UninstallProgram,{APP_NAME} mpv}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{APP_DISP_NAME} mpv"; Filename: "{app}\{APP_NAME}.exe"; AppUserModelID: "{APP_ID}"; Tasks: desktopicon

[Run]
Filename: "{app}\{APP_NAME}.exe"; Flags: nowait postinstall skipifsilent 64bit; Description: "{cm:LaunchProgram,{APP_NAME}}"

[Registry]
{APP_FILE_ASSOCIATIONS}
Root: HKCR; SubKey: "Local Settings\Software\Microsoft\Windows\Shell\MuiCache"; ValueType: string; ValueName: "{app}\{APP_NAME}.exe.FriendlyAppName"; ValueData: "{APP_DISP_NAME}"; Flags: uninsdeletevalue
Root: HKCR; SubKey: "Local Settings\Software\Microsoft\Windows\Shell\MuiCache"; ValueType: string; ValueName: "{app}\{APP_NAME}.exe.ApplicationCompany"; ValueData: "{APP_AUTHOR}"; Flags: uninsdeletevalue
