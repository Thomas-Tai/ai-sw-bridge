"""
Auto-generated SOLIDWORKS API constants from decompiled CHM.

DO NOT HAND-EDIT. Regenerate by running:
  tools/chm_extract.py batch tools/_api_extract_input.json docs/api_reference.json
  tools/gen_sw_types.py docs/api_reference.json src/ai_sw_bridge/sw_types.py

This file contains:
  - Enum constants (one per enum value, name-prefixed for easy access)
  - A METHOD_SIGNATURES dict mapping fully-qualified method names to their
    arg-name lists + arg-count. Used by builder.py for runtime arg-count
    assertion (catches CHM-mismatched calls early).
"""

from __future__ import annotations


# -----------------------------------------------------------------------------
# Enum constants
# -----------------------------------------------------------------------------

# swChamferType_e: Chamfer types.
SW_CHAMFER_ANGLE_DISTANCE = 1  # swChamferAngleDistance
SW_CHAMFER_DISTANCE_DISTANCE = 2  # swChamferDistanceDistance
SW_CHAMFER_VERTEX = 3  # swChamferVertex
SW_CHAMFER_EQUAL_DISTANCE = 16  # swChamferEqualDistance

# swDimensionType_e: Types of dimensions.
SW_DIMENSION_TYPE_UNKNOWN = (
    0  # swDimensionTypeUnknown -- Dimension type could not be determined
)
SW_ORDINATE_DIMENSION = (
    1  # swOrdinateDimension -- Base ordinate and its subordinates are of this type
)
SW_LINEAR_DIMENSION = 2  # swLinearDimension -- Linear dimension type
SW_ANGULAR_DIMENSION = 3  # swAngularDimension -- Angular dimension type
SW_ARC_LENGTH_DIMENSION = 4  # swArcLengthDimension -- Arc length dimension type
SW_RADIAL_DIMENSION = 5  # swRadialDimension -- Radial dimension
SW_DIAMETER_DIMENSION = 6  # swDiameterDimension -- Diameter dimension
SW_HOR_ORDINATE_DIMENSION = 7  # swHorOrdinateDimension -- Horizontal ordinate dimension
SW_VERT_ORDINATE_DIMENSION = 8  # swVertOrdinateDimension -- Vertical ordinate dimension
SW_ZAXIS_DIMENSION = 9  # swZAxisDimension
SW_CHAMFER_DIMENSION = 10  # swChamferDimension
SW_HOR_LINEAR_DIMENSION = 11  # swHorLinearDimension -- Horizontal linear dimension
SW_VERT_LINEAR_DIMENSION = 12  # swVertLinearDimension -- Vertical linear dimension
SW_SCALAR_DIMENSION = 13  # swScalarDimension
SW_RADIAL_LINEAR_DIMENSION = (
    14  # swRadialLinearDimension -- Doubled distance radial dimension
)
SW_DIAMETRIC_LINEAR_DIMENSION = (
    15  # swDiametricLinearDimension -- Doubled distance linear dimension
)
SW_ANGULAR_ORDINATE_DIMENSION = (
    16  # swAngularOrdinateDimension -- Angular ordinate dimension
)

# swDocumentTypes_e: Document types.
SW_DOC_NONE = 0  # swDocNONE
SW_DOC_PART = 1  # swDocPART
SW_DOC_ASSEMBLY = 2  # swDocASSEMBLY
SW_DOC_DRAWING = 3  # swDocDRAWING
SW_DOC_SDM = 4  # swDocSDM
SW_DOC_LAYOUT = 5  # swDocLAYOUT
SW_DOC_IMPORTED_PART = 6  # swDocIMPORTED_PART
SW_DOC_IMPORTED_ASSEMBLY = 7  # swDocIMPORTED_ASSEMBLY

# swEndConditions_e: End conditions for creation of a variety of features.
SW_END_COND_BLIND = 0  # swEndCondBlind
SW_END_COND_THROUGH_ALL = 1  # swEndCondThroughAll
SW_END_COND_THROUGH_NEXT = 2  # swEndCondThroughNext
SW_END_COND_UP_TO_VERTEX = (
    3  # swEndCondUpToVertex -- Do not use; superseded by swEndCondUpToSelection
)
SW_END_COND_UP_TO_SURFACE = (
    4  # swEndCondUpToSurface -- Do not use; superseded by swEndCondUpToSelection
)
SW_END_COND_OFFSET_FROM_SURFACE = 5  # swEndCondOffsetFromSurface
SW_END_COND_MID_PLANE = 6  # swEndCondMidPlane
SW_END_COND_UP_TO_BODY = 7  # swEndCondUpToBody
SW_END_COND_THROUGH_ALL_BOTH = 9  # swEndCondThroughAllBoth
SW_END_COND_UP_TO_SELECTION = 10  # swEndCondUpToSelection
SW_END_COND_UP_TO_NEXT = 11  # swEndCondUpToNext

# swFeatureChamferOption_e: Chamfer feature options. Bitmask.
SW_FEATURE_CHAMFER_FLIP_DIRECTION = 1  # swFeatureChamferFlipDirection
SW_FEATURE_CHAMFER_KEEP_FEATURE = 2  # swFeatureChamferKeepFeature
SW_FEATURE_CHAMFER_TANGENT_PROPAGATION = 4  # swFeatureChamferTangentPropagation
SW_FEATURE_CHAMFER_PROPAGATE_FEAT_TO_PARTS = 8  # swFeatureChamferPropagateFeatToParts

# swFeatureScope_e: Feature scope options.
SW_FEATURE_SCOPE_ALL_BODIES = 0  # swFeatureScope_AllBodies -- All of the bodies in the multibody part are affected by the Mirror feature.
SW_FEATURE_SCOPE_SELECTED_BODIES_WITH_AUTO_SELECT = 1  # swFeatureScope_SelectedBodiesWithAutoSelect -- Only the specified bodies in the multibody part are affected by the Mirror feature when AutoSelect is true.
SW_FEATURE_SCOPE_SELECTED_BODIES_WITH_OUT_AUTO_SELECT = 2  # swFeatureScope_SelectedBodiesWithOutAutoSelect -- Only the specified bodies in the multibody part are affected by the Mirror feature when AutoSelect is false.

# swSelectType_e: Values for types of returned IDs.

# swStartConditions_e: Start conditions.
SW_START_SKETCH_PLANE = 0  # swStartSketchPlane
SW_START_SURFACE = 1  # swStartSurface
SW_START_VERTEX = 2  # swStartVertex
SW_START_OFFSET = 3  # swStartOffset

# swThinWallType_e: Thin wall types.
SW_THIN_WALL_ONE_DIRECTION = 0  # swThinWallOneDirection
SW_THIN_WALL_OPP_DIRECTION = 1  # swThinWallOppDirection
SW_THIN_WALL_MID_PLANE = 2  # swThinWallMidPlane
SW_THIN_WALL_TWO_DIRECTION = 3  # swThinWallTwoDirection

# -----------------------------------------------------------------------------
# Method signatures (for arg-count validation)
# -----------------------------------------------------------------------------

METHOD_SIGNATURES: dict[str, dict[str, object]] = {
    "IEquationMgr.Add2": {
        "args_count": 3,
        "arg_names": ["Index", "Equation", "Solve"],
        "arg_types": ["system.int", "system.string", "system.bool"],
        "return_type": "System.int",
        "summary": "Adds an equation at the specified index.",
    },
    "IFeature.GetNextFeature": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the next feature in the part.",
    },
    "IFeature.GetTypeName": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.string",
        "summary": 'Gets the type of feature. NOTE: To get the underlying type of feature of an Instant3D feature (i.e., "ICE"), call this method; otherwise, call IFeature::GetTypeName2.',
    },
    "IFeatureManager.CreateDefinition": {
        "args_count": 1,
        "arg_names": ["Type"],
        "arg_types": ["system.int"],
        "return_type": "System.object",
        "summary": "Creates a feature data object of the specified type.",
    },
    "IFeatureManager.CreateFeature": {
        "args_count": 1,
        "arg_names": ["FeatureData"],
        "arg_types": ["system.object"],
        "return_type": "Feature",
        "summary": "Creates the specified feature.",
    },
    "IFeatureManager.FeatureCircularPattern5": {
        "args_count": 14,
        "arg_names": [
            "Number",
            "Spacing",
            "FlipDirection",
            "DName",
            "GeometryPattern",
            "EqualSpacing",
            "VaryInstance",
            "SyncSubAssemblies",
            "BDir2",
            "BSymmetric",
            "Number2",
            "Spacing2",
            "DName2",
            "EqualSpacing2",
        ],
        "arg_types": [
            "system.int",
            "system.double",
            "system.bool",
            "system.string",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.int",
            "system.double",
            "system.string",
            "system.bool",
        ],
        "return_type": "Feature",
        "summary": "Obsolete. See IFeatureManager::CreateFeature and the Remarks in ICircularPatternFeatureData and ILocalCircularPatternFeatureData.",
    },
    "IFeatureManager.FeatureCut4": {
        "args_count": 27,
        "arg_names": [
            "Sd",
            "Flip",
            "Dir",
            "T1",
            "T2",
            "D1",
            "D2",
            "Dchk1",
            "Dchk2",
            "Ddir1",
            "Ddir2",
            "Dang1",
            "Dang2",
            "OffsetReverse1",
            "OffsetReverse2",
            "TranslateSurface1",
            "TranslateSurface2",
            "NormalCut",
            "UseFeatScope",
            "UseAutoSelect",
            "AssemblyFeatureScope",
            "AutoSelectComponents",
            "PropagateFeatureToParts",
            "T0",
            "StartOffset",
            "FlipStartOffset",
            "OptimizeGeometry",
        ],
        "arg_types": [
            "system.bool",
            "system.bool",
            "system.bool",
            "system.int",
            "system.int",
            "system.double",
            "system.double",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.double",
            "system.double",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.int",
            "system.double",
            "system.bool",
            "system.bool",
        ],
        "return_type": "Feature",
        "summary": "Creates a cut extrude feature.",
    },
    "IFeatureManager.FeatureExtrusion2": {
        "args_count": 23,
        "arg_names": [
            "Sd",
            "Flip",
            "Dir",
            "T1",
            "T2",
            "D1",
            "D2",
            "Dchk1",
            "Dchk2",
            "Ddir1",
            "Ddir2",
            "Dang1",
            "Dang2",
            "OffsetReverse1",
            "OffsetReverse2",
            "TranslateSurface1",
            "TranslateSurface2",
            "Merge",
            "UseFeatScope",
            "UseAutoSelect",
            "T0",
            "StartOffset",
            "FlipStartOffset",
        ],
        "arg_types": [
            "system.bool",
            "system.bool",
            "system.bool",
            "system.int",
            "system.int",
            "system.double",
            "system.double",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.double",
            "system.double",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.int",
            "system.double",
            "system.bool",
        ],
        "return_type": "Feature",
        "summary": "Obsolete. Superseded by IFeatureManager::FeatureExtrusion3.",
    },
    "IFeatureManager.FeatureExtrusion3": {
        "args_count": 23,
        "arg_names": [
            "Sd",
            "Flip",
            "Dir",
            "T1",
            "T2",
            "D1",
            "D2",
            "Dchk1",
            "Dchk2",
            "Ddir1",
            "Ddir2",
            "Dang1",
            "Dang2",
            "OffsetReverse1",
            "OffsetReverse2",
            "TranslateSurface1",
            "TranslateSurface2",
            "Merge",
            "UseFeatScope",
            "UseAutoSelect",
            "T0",
            "StartOffset",
            "FlipStartOffset",
        ],
        "arg_types": [
            "system.bool",
            "system.bool",
            "system.bool",
            "system.int",
            "system.int",
            "system.double",
            "system.double",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.double",
            "system.double",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.int",
            "system.double",
            "system.bool",
        ],
        "return_type": "Feature",
        "summary": "Creates an extruded feature.",
    },
    "IFeatureManager.FeatureLinearPattern5": {
        "args_count": 22,
        "arg_names": [
            "Num1",
            "Spacing1",
            "Num2",
            "Spacing2",
            "FlipDir1",
            "FlipDir2",
            "DName1",
            "DName2",
            "GeometryPattern",
            "VaryInstance",
            "HasOffset1",
            "HasOffset2",
            "CtrlByNum1",
            "CtrlByNum2",
            "FromCentroid1",
            "FromCentroid2",
            "RevOffset1",
            "RevOffset2",
            "Offset1",
            "Offset2",
            "D2PatternSeedOnly",
            "SyncSubAssemblies",
        ],
        "arg_types": [
            "system.int",
            "system.double",
            "system.int",
            "system.double",
            "system.bool",
            "system.bool",
            "system.string",
            "system.string",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.double",
            "system.double",
            "system.bool",
            "system.bool",
        ],
        "return_type": "Feature",
        "summary": "Obsolete. See IFeatureManager::CreateFeature and the Remarks in ILinearPatternFeatureData and ILocalLinearPatternFeatureData.",
    },
    "IFeatureManager.FeatureRevolve2": {
        "args_count": 20,
        "arg_names": [
            "SingleDir",
            "IsSolid",
            "IsThin",
            "IsCut",
            "ReverseDir",
            "BothDirectionUpToSameEntity",
            "Dir1Type",
            "Dir2Type",
            "Dir1Angle",
            "Dir2Angle",
            "OffsetReverse1",
            "OffsetReverse2",
            "OffsetDistance1",
            "OffsetDistance2",
            "ThinType",
            "ThinThickness1",
            "ThinThickness2",
            "Merge",
            "UseFeatScope",
            "UseAutoSelect",
        ],
        "arg_types": [
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.int",
            "system.int",
            "system.double",
            "system.double",
            "system.bool",
            "system.bool",
            "system.double",
            "system.double",
            "system.int",
            "system.double",
            "system.double",
            "system.bool",
            "system.bool",
            "system.bool",
        ],
        "return_type": "Feature",
        "summary": "Creates a base-, boss-, or cut-revolve feature.",
    },
    "IFeatureManager.InsertFeatureChamfer": {
        "args_count": 8,
        "arg_names": [
            "Options",
            "ChamferType",
            "Width",
            "Angle",
            "OtherDist",
            "VertexChamDist1",
            "VertexChamDist2",
            "VertexChamDist3",
        ],
        "arg_types": [
            "system.int",
            "system.int",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
        ],
        "return_type": "Feature",
        "summary": "Inserts a chamfer.",
    },
    "IFeatureManager.InsertMirrorFeature2": {
        "args_count": 5,
        "arg_names": [
            "BMirrorBody",
            "BGeometryPattern",
            "BMerge",
            "BKnit",
            "ScopeOptions",
        ],
        "arg_types": [
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.int",
        ],
        "return_type": "Feature",
        "summary": "Mirrors selected features, faces, bodies, and structure systems about a selected plane or planar face.",
    },
    "IFeatureManager.SimpleHole2": {
        "args_count": 23,
        "arg_names": [
            "Dia",
            "Sd",
            "Flip",
            "Dir",
            "T1",
            "T2",
            "D1",
            "D2",
            "Dchk1",
            "Dchk2",
            "Ddir1",
            "Ddir2",
            "Dang1",
            "Dang2",
            "OffsetReverse1",
            "OffsetReverse2",
            "TranslateSurface1",
            "TranslateSurface2",
            "UseFeatScope",
            "UseAutoSelect",
            "AssemblyFeatureScope",
            "AutoSelectComponents",
            "PropagateFeatureToParts",
        ],
        "arg_types": [
            "system.double",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.int",
            "system.int",
            "system.double",
            "system.double",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.double",
            "system.double",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
        ],
        "return_type": "Feature",
        "summary": "Inserts a simple hole feature.",
    },
    "IModelDoc2.AddDimension2": {
        "args_count": 3,
        "arg_names": ["X", "Y", "Z"],
        "arg_types": ["system.double", "system.double", "system.double"],
        "return_type": "System.object",
        "summary": "Creates a display dimension at the specified location for selected entities.",
    },
    "IModelDoc2.ClearSelection2": {
        "args_count": 1,
        "arg_names": ["All"],
        "arg_types": ["system.bool"],
        "return_type": "void",
        "summary": "Clears the selection list.",
    },
    "IModelDoc2.EditRebuild3": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.bool",
        "summary": "Rebuilds only those features that need to be rebuilt in the active configuration in the model.",
    },
    "IModelDoc2.EditUndo2": {
        "args_count": 1,
        "arg_names": ["Steps"],
        "arg_types": ["system.int"],
        "return_type": "void",
        "summary": "Undoes the specified number of actions in the active SOLIDWORKS session.",
    },
    "IModelDoc2.FeatureByPositionReverse": {
        "args_count": 1,
        "arg_names": ["Num"],
        "arg_types": ["system.int"],
        "return_type": "System.object",
        "summary": "Gets the nth from last feature in the document.",
    },
    "IModelDoc2.GetFeatureCount": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.int",
        "summary": "Gets the number of features in this document.",
    },
    "IModelDoc2.Parameter": {
        "args_count": 1,
        "arg_names": ["StringIn"],
        "arg_types": ["system.string"],
        "return_type": "System.object",
        "summary": "Gets the specified parameter.",
    },
    "IModelDoc2.SaveBMP": {
        "args_count": 3,
        "arg_names": ["FileNameIn", "WidthIn", "HeightIn"],
        "arg_types": ["system.string", "system.int", "system.int"],
        "return_type": "System.bool",
        "summary": "Saves the current view as a bitmap (BMP) file.",
    },
    "IModelDoc2.SelectByID": {
        "args_count": 5,
        "arg_names": ["SelID", "SelParams", "X", "Y", "Z"],
        "arg_types": [
            "system.string",
            "system.string",
            "system.double",
            "system.double",
            "system.double",
        ],
        "return_type": "System.bool",
        "summary": "Obsolete. Superseded by IModelDocExtension::SelectByID2.",
    },
    "IModelDocExtension.SelectByID2": {
        "args_count": 9,
        "arg_names": [
            "Name",
            "Type",
            "X",
            "Y",
            "Z",
            "Append",
            "Mark",
            "Callout",
            "SelectOption",
        ],
        "arg_types": [
            "system.string",
            "system.string",
            "system.double",
            "system.double",
            "system.double",
            "system.bool",
            "system.int",
            "callout",
            "system.int",
        ],
        "return_type": "System.bool",
        "summary": "Selects the specified entity.",
    },
    "ISketchManager.CreateCenterLine": {
        "args_count": 6,
        "arg_names": ["X1", "Y1", "Z1", "X2", "Y2", "Z2"],
        "arg_types": [
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
        ],
        "return_type": "SketchSegment",
        "summary": "Creates a center line between the specified points.",
    },
    "ISketchManager.CreateCenterRectangle": {
        "args_count": 6,
        "arg_names": ["X1", "Y1", "Z1", "X2", "Y2", "Z2"],
        "arg_types": [
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
        ],
        "return_type": "System.object",
        "summary": "Creates a center rectangle.",
    },
    "ISketchManager.CreateCircle": {
        "args_count": 6,
        "arg_names": ["XC", "YC", "Zc", "Xp", "Yp", "Zp"],
        "arg_types": [
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
        ],
        "return_type": "SketchSegment",
        "summary": "Creates a circle based on a center point and a point on the circle.",
    },
    "ISketchManager.CreateCornerRectangle": {
        "args_count": 6,
        "arg_names": ["X1", "Y1", "Z1", "X2", "Y2", "Z2"],
        "arg_types": [
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
        ],
        "return_type": "System.object",
        "summary": "Creates a corner rectangle.",
    },
    "ISketchManager.InsertSketch": {
        "args_count": 1,
        "arg_names": ["UpdateEditRebuild"],
        "arg_types": ["system.bool"],
        "return_type": "void",
        "summary": "Inserts a new sketch in the current part or assembly document.",
    },
    "ISldWorks.GetUserPreferenceStringValue": {
        "args_count": 1,
        "arg_names": ["UserPreference"],
        "arg_types": ["system.int"],
        "return_type": "System.string",
        "summary": "Gets system default user preference values.",
    },
    "ISldWorks.GetUserPreferenceToggle": {
        "args_count": 1,
        "arg_names": ["UserPreferenceToggle"],
        "arg_types": ["system.int"],
        "return_type": "System.bool",
        "summary": "Gets document default user preference values.",
    },
    "ISldWorks.NewDocument": {
        "args_count": 4,
        "arg_names": ["TemplateName", "PaperSize", "Width", "Height"],
        "arg_types": ["system.string", "system.int", "system.double", "system.double"],
        "return_type": "System.object",
        "summary": "Creates a new document based on the specified template.",
    },
    "ISldWorks.SetUserPreferenceToggle": {
        "args_count": 2,
        "arg_names": ["UserPreferenceValue", "OnFlag"],
        "arg_types": ["system.int", "system.bool"],
        "return_type": "void",
        "summary": "Sets system default user preference values.",
    },
}


def assert_args(fq_method: str, args: tuple) -> None:
    """Sanity-check that a call has the documented arg count. Raise
    ValueError on mismatch to catch CHM-vs-call drift at runtime."""
    sig = METHOD_SIGNATURES.get(fq_method)
    if sig is None:
        return  # uncatalogued -- trust the caller
    expected = sig["args_count"]
    if len(args) != expected:
        names = sig["arg_names"]
        raise ValueError(
            f"{fq_method} expects {expected} args, got {len(args)}. "
            f"Per CHM signature: {names}"
        )
