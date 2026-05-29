' Spike v0.15 S-PERSIST VBA oracle.
' Paste into a Part-document module, press F5. Early binding handles the
' ByRef Error out-param natively, so this isolates whether the Python
' PARTIAL is a marshaling limitation rather than an API one.
Option Explicit
Sub ProbePersistRoundTrip()
    Dim swApp As Object, Part As Object, ext As Object
    Dim bodies As Variant, body As Object, faces As Variant, f As Object
    Dim pid As Variant, obj As Object, errCode As Long
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    Set ext = Part.Extension
    bodies = Part.GetBodies2(0, True)
    If IsEmpty(bodies) Then MsgBox "No solid body": Exit Sub
    Set body = bodies(0)
    faces = body.GetFaces
    Set f = faces(0)
    pid = ext.GetPersistReference3(f)
    Part.ForceRebuild3 False
    Set obj = ext.GetObjectByPersistReference3(pid, errCode)
    If obj Is Nothing Then
        MsgBox "VBA round-trip FAILED, errCode=" & errCode
    Else
        MsgBox "VBA round-trip OK, errCode=" & errCode & _
               ", selectable=" & obj.Select2(False, 0)
    End If
End Sub
