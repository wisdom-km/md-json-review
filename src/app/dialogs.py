"""Native Windows pickers. The browser cannot see a real local path."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from core.convert import ConvertError

_TITLES = {
    "book": "选择 OCR 书目录",
    "pdf": "选择原始 PDF",
    "export": "选择导出文件夹",
}


def pick_path(kind: str) -> str:
    """Open a folder or PDF dialog. An empty string means the user cancelled."""
    if kind not in _TITLES:
        raise ConvertError("BAD_REQUEST", "不知道要选择什么。")
    handle = tempfile.NamedTemporaryFile(prefix="md-json-pick-", suffix=".txt", delete=False)
    handle.close()
    out = Path(handle.name)
    env = os.environ.copy()
    env["MD_JSON_PICK_OUT"] = str(out)
    env["MD_JSON_PICK_KIND"] = kind
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-Command", _SCRIPT],
            env=env,
            capture_output=True,
            timeout=180,
            check=False,
            creationflags=flags,
        )
        if not out.is_file():
            raise ConvertError("PICK_FAILED", "没有打开选择窗口。")
        text = out.read_text(encoding="utf-8-sig").strip().strip("\ufeff")
        if completed.returncode != 0 and not text:
            raise ConvertError("PICK_FAILED", "没有打开选择窗口。")
        return text
    except subprocess.TimeoutExpired:
        raise ConvertError("PICK_FAILED", "选择窗口等待太久，已取消。") from None
    finally:
        if out.exists():
            out.unlink()


_SCRIPT = r"""
$ErrorActionPreference = "Stop"
$path = ""
$owner = $null
try {
  Add-Type -AssemblyName System.Windows.Forms
  Add-Type -AssemblyName System.Drawing
  [System.Windows.Forms.Application]::EnableVisualStyles()
  $owner = New-Object System.Windows.Forms.Form
  $owner.TopMost = $true
  $owner.ShowInTaskbar = $false
  $owner.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedToolWindow
  $owner.StartPosition = "CenterScreen"
  $owner.Size = New-Object System.Drawing.Size(1, 1)
  $owner.Opacity = 0
  $owner.Show()
  $owner.Activate()
  Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
public struct MdJsonFilterSpec {
    [MarshalAs(UnmanagedType.LPWStr)] public string Name;
    [MarshalAs(UnmanagedType.LPWStr)] public string Spec;
}

public class MdJsonFolderDialog {
    public static string Prepare() {
        Create(true);
        IFileOpenDialog dialog = Create(false);
        dialog.SetFileTypes(1, new[] { new MdJsonFilterSpec { Name = "PDF (*.pdf)", Spec = "*.pdf" } });
        var events = new KeepFileInDialog();
        uint cookie;
        dialog.Advise(events, out cookie);
        dialog.Unadvise(cookie);
        return "ok";
    }

    public static string Pick(IntPtr owner, string title, string initial) {
        IFileOpenDialog dialog = Create(true);
        dialog.SetTitle(title);
        dialog.SetOkButtonLabel("选择文件夹");
        dialog.SetFileNameLabel("文件夹");
        UseFolder(dialog, initial);
        if (dialog.Show(owner) != 0) return "";
        return ReadResult(dialog);
    }

    public static string PickFile(IntPtr owner, string title, string initial) {
        IFileOpenDialog dialog = Create(false);
        dialog.SetTitle(title);
        dialog.SetOkButtonLabel("打开");
        dialog.SetFileNameLabel("文件名");
        dialog.SetDefaultExtension("pdf");
        dialog.SetFileTypes(1, new[] { new MdJsonFilterSpec { Name = "PDF (*.pdf)", Spec = "*.pdf" } });
        UseFolder(dialog, initial);
        var events = new KeepFileInDialog();
        uint cookie;
        dialog.Advise(events, out cookie);
        try {
            if (dialog.Show(owner) != 0) return "";
            return ReadResult(dialog);
        } finally {
            dialog.Unadvise(cookie);
        }
    }

    static void UseFolder(IFileOpenDialog dialog, string initial) {
        if (string.IsNullOrEmpty(initial)) return;
        Guid iid = typeof(IShellItem).GUID;
        IShellItem start;
        if (SHCreateItemFromParsingName(initial, IntPtr.Zero, ref iid, out start) == 0) {
            dialog.SetFolder(start);
        }
    }

    static string ReadResult(IFileOpenDialog dialog) {
        IShellItem item;
        dialog.GetResult(out item);
        IntPtr psz;
        item.GetDisplayName(0x80058000, out psz);
        string picked = Marshal.PtrToStringUni(psz);
        Marshal.FreeCoTaskMem(psz);
        return picked ?? "";
    }

    static IFileOpenDialog Create(bool pickFolders) {
        IFileOpenDialog dialog = (IFileOpenDialog)new FileOpenDialogRCW();
        uint options;
        dialog.GetOptions(out options);
        if (pickFolders) dialog.SetOptions(options | 0x20 | 0x40 | 0x800);
        else dialog.SetOptions((options | 0x4 | 0x40 | 0x800 | 0x1000) & ~0x20u);
        return dialog;
    }

    [ClassInterface(ClassInterfaceType.None)]
    public class KeepFileInDialog : IFileDialogEvents {
        public int OnFileOk(IFileOpenDialog pfd) { return 0; }
        public int OnFolderChanging(IFileOpenDialog pfd, IShellItem psiFolder) {
            try {
                uint attrs;
                psiFolder.GetAttributes(0x20000000, out attrs);
                if ((attrs & 0x20000000) != 0) return 0;
                IntPtr psz;
                psiFolder.GetDisplayName(0x80058000, out psz);
                string path = Marshal.PtrToStringUni(psz);
                Marshal.FreeCoTaskMem(psz);
                if (!string.IsNullOrEmpty(path)) pfd.SetFileName(path);
            } catch (Exception) {
                return 0;
            }
            return 1;
        }
        public int OnFolderChange(IFileOpenDialog pfd) { return 0; }
        public int OnSelectionChange(IFileOpenDialog pfd) { return 0; }
        public int OnShareViolation(IFileOpenDialog pfd, IShellItem psi, out uint pResponse) {
            pResponse = 0;
            return 0;
        }
        public int OnTypeChange(IFileOpenDialog pfd) { return 0; }
        public int OnOverwrite(IFileOpenDialog pfd, IShellItem psi, out uint pResponse) {
            pResponse = 0;
            return 0;
        }
    }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = true)]
    static extern int SHCreateItemFromParsingName(
        [MarshalAs(UnmanagedType.LPWStr)] string pszPath,
        IntPtr pbc,
        ref Guid riid,
        out IShellItem ppv);

    [ComImport, Guid("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")]
    class FileOpenDialogRCW {}

    [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IShellItem {
        void BindToHandler(IntPtr pbc, [MarshalAs(UnmanagedType.LPStruct)] Guid bhid, [MarshalAs(UnmanagedType.LPStruct)] Guid riid, out IntPtr ppv);
        void GetParent(out IShellItem ppsi);
        void GetDisplayName(uint sigdnName, out IntPtr ppszName);
        void GetAttributes(uint sfgaoMask, out uint psfgaoAttribs);
        void Compare(IShellItem psi, uint hint, out int piOrder);
    }

    [ComImport, Guid("d57c7288-d4ad-4768-be02-9d969532d960")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IFileOpenDialog {
        [PreserveSig] int Show(IntPtr parent);
        void SetFileTypes(uint cFileTypes, [MarshalAs(UnmanagedType.LPArray, SizeParamIndex = 0)] MdJsonFilterSpec[] rgFilterSpec);
        void SetFileTypeIndex(uint iFileType);
        void GetFileTypeIndex(out uint piFileType);
        void Advise(IFileDialogEvents pfde, out uint pdwCookie);
        void Unadvise(uint dwCookie);
        void SetOptions(uint fos);
        void GetOptions(out uint fos);
        void SetDefaultFolder(IShellItem psi);
        void SetFolder(IShellItem psi);
        void GetFolder(out IShellItem ppsi);
        void GetCurrentSelection(out IShellItem ppsi);
        void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string pszName);
        void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string pszName);
        void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string pszTitle);
        void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string pszText);
        void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string pszLabel);
        void GetResult(out IShellItem ppsi);
        void AddPlace(IShellItem psi, int fdap);
        void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string pszDefaultExtension);
        void Close(int hr);
        void SetClientGuid([MarshalAs(UnmanagedType.LPStruct)] Guid guid);
        void ClearClientData();
        void SetFilter(IntPtr pFilter);
        void GetResults(out IntPtr ppenum);
        void GetSelectedItems(out IntPtr ppsai);
    }

    [ComImport, Guid("973510DB-7D7F-452B-8975-74A85828D354")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IFileDialogEvents {
        [PreserveSig] int OnFileOk(IFileOpenDialog pfd);
        [PreserveSig] int OnFolderChanging(IFileOpenDialog pfd, IShellItem psiFolder);
        [PreserveSig] int OnFolderChange(IFileOpenDialog pfd);
        [PreserveSig] int OnSelectionChange(IFileOpenDialog pfd);
        [PreserveSig] int OnShareViolation(IFileOpenDialog pfd, IShellItem psi, out uint pResponse);
        [PreserveSig] int OnTypeChange(IFileOpenDialog pfd);
        [PreserveSig] int OnOverwrite(IFileOpenDialog pfd, IShellItem psi, out uint pResponse);
    }
}
'@
  $desktop = [Environment]::GetFolderPath("Desktop")
  if ($env:MD_JSON_PICK_KIND -eq "__compile") {
    $path = [MdJsonFolderDialog]::Prepare()
  } elseif ($env:MD_JSON_PICK_KIND -eq "pdf") {
    $path = [MdJsonFolderDialog]::PickFile($owner.Handle, "选择原始 PDF", $desktop)
  } else {
    $title = "选择 OCR 书目录"
    if ($env:MD_JSON_PICK_KIND -eq "export") { $title = "选择导出文件夹" }
    $path = [MdJsonFolderDialog]::Pick($owner.Handle, $title, $desktop)
  }
} finally {
  if ($null -ne $owner) { $owner.Dispose() }
  $encoding = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($env:MD_JSON_PICK_OUT, $path, $encoding)
}
"""


if sys.platform != "win32":  # pragma: no cover - this tool runs on the user's Windows PC
    def pick_path(kind: str) -> str:  # type: ignore[misc]
        raise ConvertError("PICK_FAILED", "选择窗口只在 Windows 上打开。")
