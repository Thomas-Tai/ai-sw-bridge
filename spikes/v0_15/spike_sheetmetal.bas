' Spike v0.15 S-SHEETMETAL VBA oracle.
' Paste into a Part-document module, press F5.
' Prereq: a blank Part is active.
' Creates a 60x40 mm sheet-metal base flange (1.5 mm / R1.5 / k=0.44),
' activates the flat-pattern config, and exports a DXF to %TEMP%\spike_sm.dxf.
' Early binding resolves arity and enum values natively, isolating whether
' a Python PARTIAL is a marshaling limitation rather than an API one.
Option Explicit
Sub ProbeSheetMetal()
    Dim swApp    As SldWorks.SldWorks
    Dim Part     As SldWorks.ModelDoc2
    Dim fm       As SldWorks.FeatureManager
    Dim sm       As SldWorks.SketchManager
    Dim ext      As SldWorks.ModelDocExtension
    Dim feat     As SldWorks.Feature
    Dim cfg      As SldWorks.Configuration
    Dim cfgNames As Variant
    Dim dxfPath  As String
    Dim i        As Integer
    Dim ok       As Boolean

    Set swApp = Application.SldWorks
    Set Part  = swApp.ActiveDoc
    Set fm    = Part.FeatureManager
    Set sm    = Part.SketchManager
    Set ext   = Part.Extension

    ' --- profile sketch on Front Plane ---
    Part.ClearSelection2 True
    Part.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0
    sm.InsertSketch True
    sm.CreateCornerRectangle -0.03, -0.02, 0, 0.03, 0.02, 0
    sm.InsertSketch True   ' close sketch — VBA closes before InsertSheetMetalBaseFlange2

    ' In VBA the sketch must be open; re-enter edit mode.
    Part.SelectByID2 "Sketch1", "SKETCH", 0, 0, 0, False, 0, Nothing, 0
    Part.EditSketch

    ' --- base flange (11-arg form) ---
    ' InsertSheetMetalBaseFlange2(thickness, reverse, bendRadius, kFactor,
    '   reliefType, reliefW, reliefD, reliefRatio, autoRelief,
    '   formFeature, mergeResult)
    Set feat = fm.InsertSheetMetalBaseFlange2( _
        0.0015, False, 0.0015, 0.44, _
        swReliefRectangular, 0.00125, 0.00125, 0.5, _
        True, False, True)

    If feat Is Nothing Then
        MsgBox "InsertSheetMetalBaseFlange2 returned Nothing"
        Exit Sub
    End If
    MsgBox "Base flange OK: " & feat.Name & " / " & feat.GetTypeName2

    Part.EditRebuild3

    ' --- flat-pattern config ---
    cfgNames = Part.GetConfigurationNames
    Dim flatName As String
    flatName = ""
    For i = 0 To UBound(cfgNames)
        If Left(cfgNames(i), 12) = "Flat Pattern" Then
            flatName = cfgNames(i)
            Exit For
        End If
    Next i

    If flatName = "" Then
        MsgBox "No Flat Pattern config found; sheet metal add-in may be off"
        Exit Sub
    End If

    ok = Part.ShowConfiguration2(flatName)
    MsgBox "ShowConfiguration2(" & Chr(34) & flatName & Chr(34) & ") = " & ok

    ' --- DXF export ---
    dxfPath = Environ("TEMP") & Chr(92) & "spike_sm.dxf"
    ok = ext.ExportToDWG2(dxfPath, Part, swExportToDWG_ExportSheetMetal, _
                          False, False, False, Nothing, Nothing, 1.0)
    MsgBox "ExportToDWG2 = " & ok & " -> " & dxfPath
End Sub
