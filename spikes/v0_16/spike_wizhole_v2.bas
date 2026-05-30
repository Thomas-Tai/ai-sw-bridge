' Spike v0.16 S-WIZHOLE-V2 VBA oracle.
' Paste into a Part with a 20x20x10 box. Tests the REAL InitializeHole path.
Option Explicit
Sub ProbeWizHoleV2()
    Dim swApp As SldWorks.SldWorks
    Dim Part  As SldWorks.ModelDoc2
    Dim fm    As SldWorks.FeatureManager
    Dim fd    As SldWorks.WizardHoleFeatureData2
    Dim feat  As SldWorks.Feature
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    Set fm = Part.FeatureManager

    Part.ClearSelection2 True
    Part.SelectByID2 "", "FACE", 0, 0, 0.01, False, 0, Nothing, 0

    Set fd = fm.CreateDefinition(swFmHoleWzd)    ' 25
    If fd Is Nothing Then MsgBox "CreateDefinition(25) Nothing": Exit Sub
    ' swWzdHole=2, swStandardAnsiMetric=1, fastener=39 (metric drill sizes)
    fd.InitializeHole 2, 1, 39, "6.0", 0          ' swEndCondBlind=0
    fd.Depth = 0.006

    Part.ClearSelection2 True
    Part.SelectByID2 "", "FACE", 0, 0, 0.01, False, 0, Nothing, 0
    Set feat = fm.CreateFeature(fd)
    If feat Is Nothing Then
        MsgBox "CreateFeature: NOTHING (placement likely needs a sketch point)"
    Else
        MsgBox "Wizard hole: " & feat.Name & " / " & feat.GetTypeName2
    End If
End Sub
