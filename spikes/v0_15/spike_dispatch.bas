' Spike v0.15 S-DISPATCH VBA oracle.
' Paste into a Part-document module, press F5.
' Early binding handles the OUT-IDispatch Callout natively, so this
' isolates whether the Python PARTIAL is a marshaler limitation rather
' than an API one.
Option Explicit
Sub ProbeDispatchModes()
    Dim swApp       As Object
    Dim Part        As Object
    Dim ext         As Object
    Dim co          As Object
    Dim ok          As Boolean
    Dim msg         As String

    Set swApp = Application.SldWorks
    Set Part  = swApp.ActiveDoc
    Set ext   = Part.Extension

    ' 1. SelectByID2 with Callout:=Nothing (late-bound-style placeholder
    '    under early binding — VBA auto-marshals the OUT-IDispatch).
    On Error Resume Next
    ok = ext.SelectByID2("Front Plane", "PLANE", 0#, 0#, 0#, _
                         False, 0, Nothing, 0)
    If Err.Number <> 0 Then
        msg = "SelectByID2(Callout:=Nothing) FAILED: 0x" & Hex(Err.Number) _
              & " " & Err.Description
        Err.Clear
    Else
        msg = "SelectByID2(Callout:=Nothing) returned " & ok
    End If
    On Error GoTo 0

    ' 2. IEntity.Select4 on the first body edge.
    Dim bodies As Variant, body As Object, edges As Variant, e As Object
    bodies = Part.GetBodies2(0, True)
    If Not IsEmpty(bodies) Then
        Set body = bodies(0)
        edges = body.GetEdges
        If Not IsEmpty(edges) Then
            Set e = edges(0)
            On Error Resume Next
            ok = e.Select4(False, Nothing)
            If Err.Number <> 0 Then
                msg = msg & Chr(10) & "IEntity.Select4(Callout:=Nothing) FAILED: " _
                      & "0x" & Hex(Err.Number) & " " & Err.Description
                Err.Clear
            Else
                msg = msg & Chr(10) & "IEntity.Select4(Callout:=Nothing) returned " & ok
            End If
            On Error GoTo 0
        End If
    End If

    ' 3. GetSelectByIDString on IFace2 (E2.1 follow-up).
    Dim faces As Variant, f As Object, s As Variant
    If Not IsEmpty(bodies) Then
        faces = bodies(0).GetFaces
        If Not IsEmpty(faces) Then
            Set f = faces(0)
            On Error Resume Next
            s = f.GetSelectByIDString
            If Err.Number <> 0 Then
                msg = msg & Chr(10) & "IFace2.GetSelectByIDString UNREACHABLE: " _
                      & "0x" & Hex(Err.Number)
                Err.Clear
            Else
                msg = msg & Chr(10) & "IFace2.GetSelectByIDString = " & CStr(s)
            End If
            On Error GoTo 0
        End If
    End If

    MsgBox msg, vbInformation, "S-DISPATCH spike"
End Sub
