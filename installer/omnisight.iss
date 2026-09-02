; OmniSight 安装包（10 文档 §10.1）。
;
; 由 tools/build.py --release 调用；**版本号与路径一律用 /D 传进来**，脚本里不写第二份
; 字面量（版本的真源是 src/omnisight/__init__.py 的 __version__）。用 Inno Setup IDE
; 直接打开时下面的默认值让它仍然能编译，产物标成 0.0.0-dev 以免被误当成发布版。
;
; 为什么要有安装版（M6 只发便携 zip，见偏离 110/117）：
; 规划中的「登录时以管理员身份启动」要求 EXE 位于**普通用户不可写的目录**，否则那条
; 无提示提权的启动项等于给任何以该用户身份运行的程序一条静默的管理员通道。把程序装进
; Program Files 是便携包做不到、而安装包唯一必须做的事。
;
; 本文件必须以 UTF-8 **带 BOM** 保存：Inno 只在见到 BOM 时才按 UTF-8 解析，否则这里的
; 中文会变成安装向导上的乱码。tools/build.py 生成/校验这一点，测试也钉住它。

#define AppName "OmniSight"

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif
#ifndef VersionQuad
  #define VersionQuad "0.0.0.0"
#endif
; 待打包的 EXE 所在目录（构建产物目录）。
#ifndef DistDir
  #define DistDir "..\dist"
#endif
; 随包分发的文件的暂存目录，由 tools/build.py 备好（README.txt / LICENSE.txt / 清单）。
#ifndef StageDir
  #define StageDir "..\build\installer"
#endif

[Setup]
; AppId 决定"这是同一个程序的升级还是另一个程序"，**永远不要改**。
AppId={{8E4F6B1A-3C7D-4E2B-9A5F-6D0C1B2E7A94}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=RavenHogwarts
VersionInfoVersion={#VersionQuad}
VersionInfoProductVersion={#VersionQuad}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppName}.exe
; 装到 Program Files 需要管理员权限——这正是安装版存在的理由，不是顺手要的权限。
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; 升级前让用户先退出正在运行的实例。这个名字就是程序自己的单实例互斥体
; （adapters/windows/single_instance.py 的 DEFAULT_MUTEX_NAME），两处必须一致。
AppMutex=Local\OmniSight.Instance
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
LicenseFile={#StageDir}\LICENSE.txt
SetupIconFile=..\assets\omnisight.ico
OutputDir={#DistDir}
OutputBaseFilename={#AppName}-Setup

[Languages]
; 只提供简体中文：界面与全部文档目前都只有中文（M6 已知限制 4），
; 装一个英文向导再进一个中文程序只会更奇怪。
Name: "zh"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: unchecked

; 刻意**不**提供"开机自启"勾选项：安装器跑在提权状态下，此时写 HKCU 有可能写进
; 另一个账户的配置单元（用别人的管理员凭据提权时）。开机自启由程序自己管——托盘
; 那一项与设置页是同一条路径，状态也只有一处真源（10 文档 §4）。

[Files]
Source: "{#DistDir}\{#AppName}.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\README.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\THIRD_PARTY_LICENSES.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\config.example.json"; DestDir: "{app}"; Flags: ignoreversion
; 注意这里**没有** portable.marker：装进 Program Files 之后同级目录不可写，
; 带上它只会让程序把数据往一个写不进去的地方放，然后启动失败。安装版的数据在
; %LOCALAPPDATA%\OmniSight\（10 文档 §2.2）。

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppName}.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; Tasks: desktopicon

[Run]
; runasoriginaluser 是必须的：安装器是提权的，不加这个标志装完启动的程序会**继承
; 管理员权限**，用户会莫名其妙看到托盘提示写着"管理员模式"。
Filename: "{app}\{#AppName}.exe"; Description: "立即运行 {#AppName}"; \
    Flags: nowait postinstall skipifsilent runasoriginaluser

[Registry]
; 只在卸载时清掉程序自己写的自启项（安装时不动它）。留着一个指向已删除 EXE 的
; Run 项不会有实际危害，但那是残留，而卸载承诺过"再无残留"（README 的完全卸载）。
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueName: "{#AppName}"; ValueType: none; Flags: uninsdeletevalue

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\{#AppName}');
    if DirExists(DataDir) then
    begin
      // 默认按钮是「否」：一个记录了几个月按键的程序，静默删库是不可接受的。
      if MsgBox('是否同时删除统计数据？' + #13#10#13#10 + DataDir + #13#10#13#10 +
                '选「否」会保留数据，重新安装后统计接着算。',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
