' Spike v0.15 S-VARFIL VBA oracle.
' Paste into a Part-document module, press F5.
' Prereq: a 20x20x10 mm box on Front Plane already present.
' Tests IVariableRadiusFilletFeatureData SAFEARRAY round-trip
' (per-edge radius write + read-back) in early binding.
' If this PASSes but Python spikes/v0_15/spike_varfil.py is PARTIAL,
' the pywin32 marshaler (not the SW API) is the wall -> Route-C signal.
Option Explicit
Sub ProbeVarRadFillet()
    Dim swApp   As SldWorks.SldWorks
    Dim Part    As SldWorks.ModelDoc2
    Dim fm      As SldWorks.FeatureManager
    Dim data    As SldWorks.SimpleFilletFeatureData2   ' late-cast; VBA resolves IVarRad
    Dim feat    As SldWorks.Feature
    Dim radii() As Double
    Dim readback As Variant
    Dim msg     As String

    Set swApp = Application.SldWorks
    Set Part  = swApp.ActiveDoc
    Set fm    = Part.FeatureManager

    ' --- 1. Get data object (swFmFillet = 1) ---
    Set data = fm.CreateDefinition(swFmFillet)
    If data Is Nothing Then
        MsgBox "CreateDefinition(swFmFillet) returned Nothing"
        Exit Sub
    End If

    ' --- 2. Switch to variable-radius mode ---
    data.FilletType = swFilletTypeVariable   ' enum value 1

    ' --- 3. SAFEARRAY write: set per-edge radius array ---
    ' Two values: start=2 mm, end=4 mm (in metres)
    ReDim radii(1)
    radii(0) = 0.002
    radii(1) = 0.004
    data.SetVariableRadiusParameters radii

    ' --- 4. Read-back ---
    readback = data.VariableRadiusParameters
    If IsEmpty(readback) Or IsNull(readback) Then
        msg = "VariableRadiusParameters read-back: EMPTY (SAFEARRAY wall)"
    ElseIf IsArray(readback) Then
        msg = "VariableRadiusParameters read-back: ARRAY len=" & _
              UBound(readback) - LBound(readback) + 1 & _
              " first=" & readback(LBound(readback)) & _
              " last=" & readback(UBound(readback))
    Else
        msg = "VariableRadiusParameters read-back: scalar=" & readback
    End If

    ' --- 5. Select edge and create feature ---
    Part.ClearSelection2 True
    ' Select bottom-front edge mid-point (Y=-0.01, Z=0)
    Part.SelectByID2 "", "EDGE", 0, -0.01, 0, False, 0, Nothing, 0
    data.Radius = 0.002   ' constant fallback

    Set feat = fm.CreateFeature(data)
    If feat Is Nothing Then
        msg = msg & Chr(10) & "CreateFeature: NOTHING returned"
    Else
        msg = msg & Chr(10) & "CreateFeature OK -> " & feat.Name & " / " & feat.GetTypeName2
    End If

    MsgBox "S-VARFIL VBA oracle:" & Chr(10) & msg
End Sub
