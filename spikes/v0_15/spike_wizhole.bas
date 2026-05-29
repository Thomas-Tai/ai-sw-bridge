' Spike v0.15 S-WIZHOLE VBA oracle.
' Paste into a Part-document module, press F5.
' Prereq: a 20x20x10 box on Front Plane (z from 0 to 10 mm).
' Creates a M6 ANSI Metric through-all hole at part position (5,0,10 mm).
' Early binding resolves IWizardHoleFeatureData2 and enum values natively,
' isolating whether a Python PARTIAL is a marshaling limitation.
Option Explicit
Sub ProbeWizardHole()
    Dim swApp       As SldWorks.SldWorks
    Dim Part        As SldWorks.ModelDoc2
    Dim fm          As SldWorks.FeatureManager
    Dim sm          As SldWorks.SketchManager
    Dim holeData    As SldWorks.WizardHoleFeatureData2
    Dim feat        As SldWorks.Feature

    Set swApp = Application.SldWorks
    Set Part  = swApp.ActiveDoc
    Set fm    = Part.FeatureManager
    Set sm    = Part.SketchManager

    ' --- placement sketch ---
    Part.ClearSelection2 True
    Part.SelectByID2 "", "FACE", 0, 0, 0.01, False, 0, Nothing, 0
    sm.InsertSketch True
    sm.CreatePoint 0.005, 0, 0
    sm.InsertSketch True

    ' --- hole data object ---
    Set holeData = fm.CreateDefinition(swFmHoleWzd)
    If holeData Is Nothing Then
        MsgBox "CreateDefinition(swFmHoleWzd) returned Nothing"
        Exit Sub
    End If

    holeData.HoleType      = swWzdHole            ' simple drill
    holeData.Standard      = "ANSI Metric"
    holeData.FastenerType  = "Hex Bolt"
    holeData.Size          = "M6"
    holeData.EndCondition  = swEndCondThroughAll

    ' --- re-select face + point ---
    Part.ClearSelection2 True
    Part.SelectByID2 "", "FACE", 0, 0, 0.01, False, 0, Nothing, 0
    Part.SelectByID2 "", "SKETCHPOINT", 0.005, 0, 0.01, True, 0, Nothing, 0

    ' --- create feature ---
    Set feat = fm.CreateFeature(holeData)
    If feat Is Nothing Then
        MsgBox "CreateFeature returned Nothing"
    Else
        MsgBox "VBA OK — feature: " & feat.Name & " type: " & feat.GetTypeName2
    End If
End Sub
