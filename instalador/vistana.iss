; Instalador de Vistana (Inno Setup 6). No se compila a mano: lo hace
; instalador\construir.ps1, que primero empaqueta la app con flet pack y le pasa
; la versión de modulos\marca.py (/DVersion=...).

#ifndef Version
  #error Compilar con instalador\construir.ps1 (falta /DVersion)
#endif

[Setup]
; El AppId identifica a la app entre versiones: no cambiarlo, o una
; actualización se instalaría al lado de la anterior en vez de reemplazarla.
AppId={{6813D7DB-3E0B-4732-BCE7-5DB947E40FF1}
AppName=Vistana
AppVersion={#Version}
AppVerName=Vistana {#Version}
AppPublisher=Vistana
DefaultDirName={autopf}\Vistana
DefaultGroupName=Vistana
DisableProgramGroupPage=yes
; Sin permisos de administrador se instala solo para el usuario actual;
; con ellos, el asistente ofrece instalar para todos.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=salida
OutputBaseFilename=Vistana-{#Version}-instalador
SetupIconFile=..\Iconos\vistana_logo.ico
UninstallDisplayIcon={app}\AnalizadorDelictual.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Una actualización con la app abierta pide cerrarla en lugar de fallar
CloseApplications=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\AnalizadorDelictual\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Vistana"; Filename: "{app}\AnalizadorDelictual.exe"
Name: "{group}\Desinstalar Vistana"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Vistana"; Filename: "{app}\AnalizadorDelictual.exe"; Tasks: escritorio

[Run]
Filename: "{app}\AnalizadorDelictual.exe"; Description: "Abrir Vistana"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Carpeta de trabajo (mapa con datos de denuncias y registro de errores).
; Los PDF y Excel exportados están donde el usuario los guardó y no se tocan.
Type: filesandordirs; Name: "{localappdata}\AnalizadorDelictual"
