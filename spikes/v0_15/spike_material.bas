' Spike v0.15 S-MATERIAL VBA oracle.
' Paste into a Part-document module and press F5.
' Prereq: SOLIDWORKS running with a blank Part active (a solid body helps
' for mass-props honesty check, but is not required for assignment probe).
' Checks SetMaterialPropertyName2 + GetMaterialPropertyName2 + GetMassProperties2.
Option Explicit
Sub ProbeMaterialAssignment()
    Dim swApp   As SldWorks.SldWorks
    Dim Part    As SldWorks.PartDoc
    Dim ext     As SldWorks.ModelDocExtension
    Dim dbName  As String
    Dim matName As String
    Dim setOk   As Boolean
    Dim rb      As Variant
    Dim props   As Variant
    Dim density As Double
    Dim msg     As String

    Set swApp = Application.SldWorks
    Set Part  = swApp.ActiveDoc
    Set ext   = Part.Extension

    dbName  = "SolidWorks Materials"
    matName = "AISI 1020 Steel (SS)"

    ' --- Mass props BEFORE assignment ---
    props = Part.GetMassProperties2(0, 1, True)
    If IsEmpty(props) Or IsNull(props) Then
        msg = "GetMassProperties2 pre: (empty)"
    ElseIf UBound(props) >= 2 And CDbl(props(0)) > 0 Then
        density = CDbl(props(2)) / CDbl(props(0))
        msg = "Pre-assignment density: " & density & " kg/m3"
    Else
        msg = "Pre-assignment density: n/a"
    End If

    ' --- Assign material ---
    setOk = Part.SetMaterialPropertyName2("", dbName, matName)
    msg = msg & Chr(10) & "SetMaterialPropertyName2 returned: " & setOk

    ' --- Read-back ---
    rb = Part.GetMaterialPropertyName2("")
    If IsArray(rb) Then
        msg = msg & Chr(10) & "GetMaterialPropertyName2 db=" & rb(0) & " name=" & rb(1)
    Else
        msg = msg & Chr(10) & "GetMaterialPropertyName2 = " & rb
    End If

    ' --- Mass props AFTER assignment ---
    props = Part.GetMassProperties2(0, 1, True)
    If IsEmpty(props) Or IsNull(props) Then
        msg = msg & Chr(10) & "GetMassProperties2 post: (empty)"
    ElseIf UBound(props) >= 2 And CDbl(props(0)) > 0 Then
        density = CDbl(props(2)) / CDbl(props(0))
        msg = msg & Chr(10) & "Post-assignment density: " & density & " kg/m3"
    Else
        msg = msg & Chr(10) & "Post-assignment density: n/a"
    End If

    MsgBox msg, vbInformation, "S-MATERIAL spike"
End Sub
