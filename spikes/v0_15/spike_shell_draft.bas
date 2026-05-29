' Spike v0.15 S-SHELL/DRAFT VBA oracle.
' Paste into a Part-document module, press F5.
' Prereq: blank Part active.  Creates two boxes (one for each probe).
' Early binding resolves arg types natively, isolating whether a Python
' PARTIAL is a marshaling limitation rather than an API one.
Option Explicit

Private Const BOX_W As Double = 0.02   ' 20 mm
Private Const BOX_H As Double = 0.02   ' 20 mm
Private Const BOX_D As Double = 0.01   ' 10 mm

Sub ProbeShellAndDraft()
    Dim swApp As SldWorks.SldWorks
    Dim Part  As SldWorks.ModelDoc2
    Dim fm    As SldWorks.FeatureManager
    Dim sk    As SldWorks.SketchManager
    Dim feat  As SldWorks.Feature

    Set swApp = Application.SldWorks
    Set Part  = swApp.ActiveDoc
    Set fm    = Part.FeatureManager
    Set sk    = Part.SketchManager

    ' ===== SHELL PROBE =====
    ' Build a 20x20x10 box on the Front Plane.
    Part.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0
    sk.InsertSketch True
    sk.CreateCornerRectangle -BOX_W / 2, -BOX_H / 2, 0, BOX_W / 2, BOX_H / 2, 0
    sk.InsertSketch True
    Set feat = fm.FeatureExtrusion2( _
        True, False, False, 0, 0, BOX_D, 0#, _
        False, False, False, False, 0#, 0#, _
        False, False, False, False, True, True, True, 0, 0#, False)
    If feat Is Nothing Then
        MsgBox "Shell: box build FAILED": GoTo DraftProbe
    End If

    ' Select the +z face and shell it.
    Part.ClearSelection2 True
    Part.SelectByID2 "", "FACE", 0, 0, BOX_D, False, 0, Nothing, 0
    Set feat = fm.InsertFeatureShell(0.002, True)   ' 2 mm wall
    If feat Is Nothing Then
        MsgBox "Shell FAIL: InsertFeatureShell returned Nothing"
    Else
        MsgBox "Shell PASS: " & feat.Name & " (" & feat.GetTypeName2 & ")"
    End If

DraftProbe:
    ' ===== DRAFT PROBE =====
    ' Build a fresh box (the shell probe hollowed the previous one).
    Part.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0
    sk.InsertSketch True
    sk.CreateCornerRectangle -BOX_W / 2, -BOX_H / 2, 0, BOX_W / 2, BOX_H / 2, 0
    sk.InsertSketch True
    Set feat = fm.FeatureExtrusion2( _
        True, False, False, 0, 0, BOX_D, 0#, _
        False, False, False, False, 0#, 0#, _
        False, False, False, False, True, True, True, 0, 0#, False)
    If feat Is Nothing Then
        MsgBox "Draft: box build FAILED": Exit Sub
    End If

    ' Select Front Plane (neutral) + +z face (to draft).
    Part.ClearSelection2 True
    Part.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0
    Part.SelectByID2 "", "FACE", 0, 0, BOX_D, True, 0, Nothing, 0

    ' 5° draft angle.
    Dim ang As Double: ang = 5# * 3.14159265358979 / 180#
    Set feat = fm.InsertDraft2(ang, False, False, False, 0#, True, ang)
    If feat Is Nothing Then
        MsgBox "Draft FAIL: InsertDraft2 returned Nothing"
    Else
        MsgBox "Draft PASS: " & feat.Name & " (" & feat.GetTypeName2 & ")"
    End If
End Sub
