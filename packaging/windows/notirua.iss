; Windows installer (M6). Built by .github/workflows/release.yml:
;   iscc /DAppVersion=0.3.0 /DSourceDir=dist\app\Notirua /DOutputDir=dist /DIconFile=build\icons-win32\notirua.ico packaging\windows\notirua.iss
; Installs for the current user by default (no administrator rights needed);
; the dialog also offers all users.

#ifndef AppVersion
  #error AppVersion is required
#endif

[Setup]
AppId={{6F0B7D2E-6C1A-4E7B-9E55-2A4F3C9D8B11}
AppName=Notirua
AppVersion={#AppVersion}
AppVerName=Notirua {#AppVersion}
AppPublisher=Jerry Leem
AppPublisherURL=https://github.com/jerry-leem/notirua
AppSupportURL=https://github.com/jerry-leem/notirua/issues
AppUpdatesURL=https://github.com/jerry-leem/notirua/releases
DefaultDirName={autopf}\Notirua
DefaultGroupName=Notirua
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\..\LICENSE
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\Notirua.exe
OutputDir={#OutputDir}
OutputBaseFilename=Notirua-{#AppVersion}-windows-x64-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

; Installing over an older version only adds and overwrites files. Old files that
; the new bundle no longer has would stay: a leftover notirua-<old>.dist-info makes
; the app report the old version. Clear the program folder first. Settings,
; components, and cache live outside {app}, so nothing of the user's is lost.
[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Notirua"; Filename: "{app}\Notirua.exe"
Name: "{autodesktop}\Notirua"; Filename: "{app}\Notirua.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Notirua.exe"; Description: "{cm:LaunchProgram,Notirua}"; Flags: nowait postinstall skipifsilent
