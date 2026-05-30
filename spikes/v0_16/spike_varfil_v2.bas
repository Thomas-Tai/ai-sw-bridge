' Spike v0.16 S-VARFIL-V2 VBA oracle.
' Paste into a Part with a 20x20x10 box. Tests multi-radius via the SIMPLE
' fillet data object (IsMultipleRadius), the path the typelib actually exposes.
Option Explicit
Sub ProbeMultiRadiusFillet()
    Dim swApp As SldWorks.SldWorks
    Dim Part  As SldWorks.ModelDoc2
    Dim fm    As SldWorks.FeatureManager
    Dim fd    As SldWorks.SimpleFilletFeatureData2
    Dim feat  As SldWorks.Feature
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    Set fm = Part.FeatureManager

    Set fd = fm.CreateDefinition(swFmFillet)        ' 1
    If fd Is Nothing Then MsgBox "CreateDefinition(1) Nothing": Exit Sub
    fd.Initialize swConstRadiusFillet                ' 0
    fd.DefaultRadius = 0.003
    fd.IsMultipleRadius = True

    Part.ClearSelection2 True
    Part.SelectByID2 "", "EDGE", 0, 0.01, 0.01, True, 0, Nothing, 0
    Part.SelectByID2 "", "EDGE", 0.01, 0, 0.01, True, 0, Nothing, 0

    Set feat = fm.CreateFeature(fd)
    If feat Is Nothing Then
        MsgBox "CreateFeature: NOTHING"
    Else
        MsgBox "Fillet: " & feat.Name & " / " & feat.GetTypeName2 & _
               "  IsMultipleRadius=" & fd.IsMultipleRadius
    End If
End Sub
