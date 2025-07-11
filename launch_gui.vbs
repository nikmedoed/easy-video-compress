Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
command = "pythonw.exe """ & scriptDir & "\compress.py"" --gui"
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = scriptDir
shell.Run command, 0, False
