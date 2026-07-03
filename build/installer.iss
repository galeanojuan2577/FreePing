; FreePing — Inno Setup Installer
; Requiere Inno Setup 6+ (https://jrsoftware.org/isdl.php)
; Compilar: iscc installer.iss

#define MyAppName "FreePing"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Diego Galeano"
#define MyAppURL "https://github.com/galeanojuan2577/FreePing"
#define MyAppExeName "FreePing.exe"

[Setup]
AppId={{B8F4E3D1-2A5C-4E7F-9D0B-1C3A5E7F9B0D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=FreePing_Setup_v{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=freeping.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableProgramGroupPage=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
Spanish.SetupWindowTitle=Instalación de {#MyAppName} v{#MyAppVersion}
Spanish.AppName={#MyAppName}
Spanish.WelcomeLabel1=Bienvenido al asistente de instalación de {#MyAppName}
Spanish.WelcomeLabel2=FreePing es tu NoPing personal, gratuito y autoalojado.%n%nUsa Oracle Cloud Free Tier + WireGuard para reducir el ping en tus juegos favoritos.%n%nSe recomienda cerrar otras aplicaciones antes de continuar.
Spanish.FinishedLabel=La instalación de {#MyAppName} se ha completado.%n%nEjecuta FreePing desde el acceso directo en el escritorio.

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"
Name: "autostart"; Description: "Iniciar FreePing al iniciar sesión"; GroupDescription: "Opciones adicionales:"

[Files]
Source: "..\dist\FreePing\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\FreePing\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Ejecutar FreePing ahora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\freeping\bin\wireguard.exe"; Parameters: "/uninstalltunnelservice freeping"; Flags: runhidden skipifdoesntexist; Check: IsWin64

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\FreePing\config.json"
Type: filesandordirs; Name: "{userappdata}\FreePing\keys\"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not WizardSilent then
      MsgBox(
        'IMPORTANTE:' + #13#10 +
        #13#10 +
        '1. WireGuard debe estar instalado en el sistema' + #13#10 +
        '   Descargar: https://www.wireguard.com/install/' + #13#10 +
        #13#10 +
        '2. Necesitas una cuenta gratuita de Oracle Cloud' + #13#10 +
        '   para aprovisionar el VPS automáticamente' + #13#10 +
        #13#10 +
        '3. Todo el tráfico del túnel es gratuito' + #13#10 +
        '   (Oracle Free Tier: 10 TB/mes salida)',
        mbInformation, MB_OK
      );
  end;
end;