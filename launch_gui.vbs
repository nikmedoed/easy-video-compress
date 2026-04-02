Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
scriptPath = scriptDir & "\compress.py"
venvPythonw = scriptDir & "\.venv\Scripts\pythonw.exe"
venvPython = scriptDir & "\.venv\Scripts\python.exe"

If fso.FileExists(venvPythonw) Then
    command = """" & venvPythonw & """ """ & scriptPath & """ --gui"
ElseIf fso.FileExists(venvPython) Then
    command = """" & venvPython & """ """ & scriptPath & """ --gui"
ElseIf shell.Run("cmd /c where pyw", 0, True) = 0 Then
    command = "pyw -3 """ & scriptPath & """ --gui"
ElseIf shell.Run("cmd /c where pythonw", 0, True) = 0 Then
    command = "pythonw """ & scriptPath & """ --gui"
Else
    command = "python """ & scriptPath & """ --gui"
End If

shell.CurrentDirectory = scriptDir
shell.Run command, 0, False
