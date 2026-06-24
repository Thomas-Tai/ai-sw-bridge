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

# swAnnotationType_e: Annotation types.
SW_CTHREAD = 1  # swCThread
SW_DATUM_TAG = 2  # swDatumTag
SW_DATUM_TARGET_SYM = 3  # swDatumTargetSym
SW_DISPLAY_DIMENSION = 4  # swDisplayDimension
SW_GTOL = 5  # swGTol
SW_NOTE = 6  # swNote
SW_SFSYMBOL = 7  # swSFSymbol
SW_WELD_SYMBOL = 8  # swWeldSymbol
SW_CUSTOM_SYMBOL = 9  # swCustomSymbol
SW_DOWEL_SYM = 10  # swDowelSym
SW_LEADER = 11  # swLeader
SW_BLOCK = 12  # swBlock
SW_CENTER_MARK_SYM = 13  # swCenterMarkSym
SW_TABLE_ANNOTATION = 14  # swTableAnnotation
SW_CENTER_LINE = 15  # swCenterLine
SW_DATUM_ORIGIN = 16  # swDatumOrigin
SW_WELD_BEAD_SYMBOL = 17  # swWeldBeadSymbol
SW_REVISION_CLOUD = 18  # swRevisionCloud
SW_PMIONLY = 19  # swPMIOnly

# swBodyOperationType_e: Body operation types.
SW_SWBODYINTERSECT = 15901  # SWBODYINTERSECT
SW_SWBODYCUT = 15902  # SWBODYCUT
SW_SWBODYADD = 15903  # SWBODYADD

# swBodyType_e: Valid body types.
SW_ALL_BODIES = -1  # swAllBodies -- All solid and sheet bodies
SW_SOLID_BODY = 0  # swSolidBody -- Solid body
SW_SHEET_BODY = 1  # swSheetBody -- Sheet body
SW_WIRE_BODY = 2  # swWireBody -- Wire body
SW_MINIMUM_BODY = 3  # swMinimumBody -- Point body
SW_GENERAL_BODY = 4  # swGeneralBody -- General, nonmanifold body
SW_EMPTY_BODY = 5  # swEmptyBody -- NULL body
SW_MESH_BODY = 6  # swMeshBody -- Mesh body
SW_GRAPHICS_BODY = 7  # swGraphicsBody -- Graphics body

# swChamferType_e: Chamfer types.
SW_CHAMFER_ANGLE_DISTANCE = 1  # swChamferAngleDistance
SW_CHAMFER_DISTANCE_DISTANCE = 2  # swChamferDistanceDistance
SW_CHAMFER_VERTEX = 3  # swChamferVertex
SW_CHAMFER_EQUAL_DISTANCE = 16  # swChamferEqualDistance

# swConstraintType_e: Sketch constraints.
SW_CONSTRAINT_TYPE_INVALIDCTYPE = 0  # swConstraintType_INVALIDCTYPE
SW_CONSTRAINT_TYPE_DISTANCE = 1  # swConstraintType_DISTANCE
SW_CONSTRAINT_TYPE_ANGLE = 2  # swConstraintType_ANGLE
SW_CONSTRAINT_TYPE_RADIUS = 3  # swConstraintType_RADIUS
SW_CONSTRAINT_TYPE_HORIZONTAL = 4  # swConstraintType_HORIZONTAL
SW_CONSTRAINT_TYPE_VERTICAL = (
    5  # swConstraintType_VERTICAL -- Applies only to sketch lines
)
SW_CONSTRAINT_TYPE_TANGENT = 6  # swConstraintType_TANGENT
SW_CONSTRAINT_TYPE_PARALLEL = 7  # swConstraintType_PARALLEL
SW_CONSTRAINT_TYPE_PERPENDICULAR = 8  # swConstraintType_PERPENDICULAR
SW_CONSTRAINT_TYPE_COINCIDENT = 9  # swConstraintType_COINCIDENT
SW_CONSTRAINT_TYPE_CONCENTRIC = 10  # swConstraintType_CONCENTRIC
SW_CONSTRAINT_TYPE_SYMMETRIC = 11  # swConstraintType_SYMMETRIC
SW_CONSTRAINT_TYPE_ATMIDDLE = 12  # swConstraintType_ATMIDDLE
SW_CONSTRAINT_TYPE_ATINTERSECT = 13  # swConstraintType_ATINTERSECT
SW_CONSTRAINT_TYPE_SAMELENGTH = 14  # swConstraintType_SAMELENGTH
SW_CONSTRAINT_TYPE_DIAMETER = 15  # swConstraintType_DIAMETER
SW_CONSTRAINT_TYPE_OFFSETEDGE = 16  # swConstraintType_OFFSETEDGE
SW_CONSTRAINT_TYPE_FIXED = 17  # swConstraintType_FIXED
SW_CONSTRAINT_TYPE_ARCANG90 = 18  # swConstraintType_ARCANG90
SW_CONSTRAINT_TYPE_ARCANG180 = 19  # swConstraintType_ARCANG180
SW_CONSTRAINT_TYPE_ARCANG270 = 20  # swConstraintType_ARCANG270
SW_CONSTRAINT_TYPE_ARCANGTOP = 21  # swConstraintType_ARCANGTOP
SW_CONSTRAINT_TYPE_ARCANGBOTTOM = 22  # swConstraintType_ARCANGBOTTOM
SW_CONSTRAINT_TYPE_ARCANGLEFT = 23  # swConstraintType_ARCANGLEFT
SW_CONSTRAINT_TYPE_ARCANGRIGHT = 24  # swConstraintType_ARCANGRIGHT
SW_CONSTRAINT_TYPE_HORIZPOINTS = 25  # swConstraintType_HORIZPOINTS
SW_CONSTRAINT_TYPE_VERTPOINTS = (
    26  # swConstraintType_VERTPOINTS -- Applies only to sketch points
)
SW_CONSTRAINT_TYPE_COLINEAR = 27  # swConstraintType_COLINEAR
SW_CONSTRAINT_TYPE_CORADIAL = 28  # swConstraintType_CORADIAL
SW_CONSTRAINT_TYPE_SNAPGRID = 29  # swConstraintType_SNAPGRID
SW_CONSTRAINT_TYPE_SNAPLENGTH = 30  # swConstraintType_SNAPLENGTH
SW_CONSTRAINT_TYPE_SNAPANGLE = 31  # swConstraintType_SNAPANGLE
SW_CONSTRAINT_TYPE_USEEDGE = 32  # swConstraintType_USEEDGE
SW_CONSTRAINT_TYPE_ELLIPSEANG90 = 33  # swConstraintType_ELLIPSEANG90
SW_CONSTRAINT_TYPE_ELLIPSEANG180 = 34  # swConstraintType_ELLIPSEANG180
SW_CONSTRAINT_TYPE_ELLIPSEANG270 = 35  # swConstraintType_ELLIPSEANG270
SW_CONSTRAINT_TYPE_ELLIPSEANGTOP = 36  # swConstraintType_ELLIPSEANGTOP
SW_CONSTRAINT_TYPE_ELLIPSEANGBOTTOM = 37  # swConstraintType_ELLIPSEANGBOTTOM
SW_CONSTRAINT_TYPE_ELLIPSEANGLEFT = 38  # swConstraintType_ELLIPSEANGLEFT
SW_CONSTRAINT_TYPE_ELLIPSEANGRIGHT = 39  # swConstraintType_ELLIPSEANGRIGHT
SW_CONSTRAINT_TYPE_ATPIERCE = 40  # swConstraintType_ATPIERCE
SW_CONSTRAINT_TYPE_DOUBLEDISTANCE = 41  # swConstraintType_DOUBLEDISTANCE
SW_CONSTRAINT_TYPE_MERGEPOINTS = 42  # swConstraintType_MERGEPOINTS
SW_CONSTRAINT_TYPE_ANGLE3P = 43  # swConstraintType_ANGLE3P
SW_CONSTRAINT_TYPE_ARCLENGTH = 44  # swConstraintType_ARCLENGTH
SW_CONSTRAINT_TYPE_NORMAL = 45  # swConstraintType_NORMAL
SW_CONSTRAINT_TYPE_NORMALPOINTS = 46  # swConstraintType_NORMALPOINTS
SW_CONSTRAINT_TYPE_SKETCHOFFSET = (
    47  # swConstraintType_SKETCHOFFSET -- Between entities of the same sketch
)
SW_CONSTRAINT_TYPE_ALONGX = 48  # swConstraintType_ALONGX
SW_CONSTRAINT_TYPE_ALONGY = 49  # swConstraintType_ALONGY
SW_CONSTRAINT_TYPE_ALONGZ = 50  # swConstraintType_ALONGZ
SW_CONSTRAINT_TYPE_ALONGXPOINTS = 51  # swConstraintType_ALONGXPOINTS
SW_CONSTRAINT_TYPE_ALONGYPOINTS = 52  # swConstraintType_ALONGYPOINTS
SW_CONSTRAINT_TYPE_ALONGZPOINTS = 53  # swConstraintType_ALONGZPOINTS
SW_CONSTRAINT_TYPE_PARALLELYZ = 54  # swConstraintType_PARALLELYZ
SW_CONSTRAINT_TYPE_PARALLELZX = 55  # swConstraintType_PARALLELZX
SW_CONSTRAINT_TYPE_INTERSECTION = 56  # swConstraintType_INTERSECTION
SW_CONSTRAINT_TYPE_PATTERNED = 57  # swConstraintType_PATTERNED
SW_CONSTRAINT_TYPE_ISOBYPOINT = 58  # swConstraintType_ISOBYPOINT -- ISO curve when its constraint parameter is determined by an external point
SW_CONSTRAINT_TYPE_SAMEISOPARAM = 59  # swConstraintType_SAMEISOPARAM -- Common relation for all pieces ( for the face ) of the surface's iso curve
SW_CONSTRAINT_TYPE_FITSPLINE = 60  # swConstraintType_FITSPLINE
SW_CONSTRAINT_TYPE_EQUALCURVATURE = 61  # swConstraintType_EQUALCURVATURE
SW_CONSTRAINT_TYPE_EQUALTANGENT = 62  # swConstraintType_EQUALTANGENT
SW_CONSTRAINT_TYPE_TANGENTFACE = 63  # swConstraintType_TANGENTFACE
SW_CONSTRAINT_TYPE_ALONGX3D = 64  # swConstraintType_ALONGX3D
SW_CONSTRAINT_TYPE_ALONGY3D = 65  # swConstraintType_ALONGY3D
SW_CONSTRAINT_TYPE_ALONGXPOINTS3D = 66  # swConstraintType_ALONGXPOINTS3D
SW_CONSTRAINT_TYPE_ALONGYPOINTS3D = 67  # swConstraintType_ALONGYPOINTS3D
SW_CONSTRAINT_TYPE_TRACTION = 68  # swConstraintType_TRACTION
SW_CONSTRAINT_TYPE_BELTTRACTION = 69  # swConstraintType_BELTTRACTION
SW_CONSTRAINT_TYPE_BLOCKFIXEDLOCK = (
    70  # swConstraintType_BLOCKFIXEDLOCK -- Lock two blocks together
)
SW_CONSTRAINT_TYPE_BLOCKNORMALLOCK = 71  # swConstraintType_BLOCKNORMALLOCK -- Lock blocks to be normal to one another (3D sketch)
SW_CONSTRAINT_TYPE_BLOCKROTATELOCK = 72  # swConstraintType_BLOCKROTATELOCK -- Lock blocks to rotate around each other (3D sketch)
SW_CONSTRAINT_TYPE_FAKESLOTCONSTRAINT = 73  # swConstraintType_FAKESLOTCONSTRAINT -- Not actually a constraint; for display purposes only
SW_CONSTRAINT_TYPE_FIXEDSLOT = 74  # swConstraintType_FIXEDSLOT -- Fix a slot
SW_CONSTRAINT_TYPE_SAMESLOTS = (
    75  # swConstraintType_SAMESLOTS -- Same slot width and length
)
SW_CONSTRAINT_TYPE_LINEARPATTCNT = 76  # swConstraintType_LINEARPATTCNT
SW_CONSTRAINT_TYPE_CIRCULARPATTCNT = 77  # swConstraintType_CIRCULARPATTCNT
SW_CONSTRAINT_TYPE_RADIALOFFSET = (
    78  # swConstraintType_RADIALOFFSET -- For routing pipe offsets
)
SW_CONSTRAINT_TYPE_PLANAROFFSET = (
    79  # swConstraintType_PLANAROFFSET -- For routing pipe offsets
)
SW_CONSTRAINT_TYPE_EQUALCURV3DALIGN = 80  # swConstraintType_EQUALCURV3DALIGN -- Aligned equal curvature between 3D splines
SW_CONSTRAINT_TYPE_FLANGEFACEDIST = 81  # swConstraintType_FLANGEFACEDIST -- Distance from virtual point to the relevant flange face
SW_CONSTRAINT_TYPE_CONICRHO = 82  # swConstraintType_CONICRHO
SW_CONSTRAINT_TYPE_C3TOUCH = 83  # swConstraintType_C3TOUCH
SW_CONSTRAINT_TYPE_DOUBLEANGLE = (
    84  # swConstraintType_DOUBLEANGLE -- Double angle display
)
SW_CONSTRAINT_TYPE_SAMECURVELENGTH = (
    85  # swConstraintType_SAMECURVELENGTH -- Equal arc/spline length
)

# swCustomInfoType_e: Custom property types.
SW_CUSTOM_INFO_UNKNOWN = 0  # swCustomInfoUnknown
SW_CUSTOM_INFO_NUMBER = 3  # swCustomInfoNumber -- Integer value
SW_CUSTOM_INFO_DOUBLE = 5  # swCustomInfoDouble -- Double value
SW_CUSTOM_INFO_YES_OR_NO = 11  # swCustomInfoYesOrNo -- Yes or No value
SW_CUSTOM_INFO_TEXT = 30  # swCustomInfoText -- Text value
SW_CUSTOM_INFO_DATE = 64  # swCustomInfoDate -- Datetime value
SW_CUSTOM_INFO_EQUATION = 105  # swCustomInfoEquation -- Equation value

# swCustomPropertyAddOption_e: Options when adding custom properties.
SW_CUSTOM_PROPERTY_ONLY_IF_NEW = (
    0  # swCustomPropertyOnlyIfNew -- Add the custom property only if it is new
)
SW_CUSTOM_PROPERTY_DELETE_AND_ADD = 1  # swCustomPropertyDeleteAndAdd -- Delete an existing custom property having the same name and add the new custom property
SW_CUSTOM_PROPERTY_REPLACE_VALUE = 2  # swCustomPropertyReplaceValue -- Replace the value of an existing custom property having the same name

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

# swDraftFacePropagationType_e: Draft face propagaton types.
SW_FACE_PROP_NONE = 0  # swFacePropNone
SW_FACE_PROP_TANGENT = 1  # swFacePropTangent
SW_FACE_PROP_ALL_LOOPS = 2  # swFacePropAllLoops
SW_FACE_PROP_INNER_LOOPS = 3  # swFacePropInnerLoops
SW_FACE_PROP_OUTER_LOOPS = 4  # swFacePropOuterLoops

# swDwgPaperSizes_e: Drawing paper sizes.
SW_DWG_PAPER_ASIZE = 0  # swDwgPaperAsize
SW_DWG_PAPER_ASIZE_VERTICAL = 1  # swDwgPaperAsizeVertical
SW_DWG_PAPER_BSIZE = 2  # swDwgPaperBsize
SW_DWG_PAPER_CSIZE = 3  # swDwgPaperCsize
SW_DWG_PAPER_DSIZE = 4  # swDwgPaperDsize
SW_DWG_PAPER_ESIZE = 5  # swDwgPaperEsize
SW_DWG_PAPER_A4SIZE = 6  # swDwgPaperA4size
SW_DWG_PAPER_A4SIZE_VERTICAL = 7  # swDwgPaperA4sizeVertical
SW_DWG_PAPER_A3SIZE = 8  # swDwgPaperA3size
SW_DWG_PAPER_A2SIZE = 9  # swDwgPaperA2size
SW_DWG_PAPER_A1SIZE = 10  # swDwgPaperA1size
SW_DWG_PAPER_A0SIZE = 11  # swDwgPaperA0size
SW_DWG_PAPERS_USER_DEFINED = 12  # swDwgPapersUserDefined

# swDwgTemplates_e: Drawing templates.
SW_DWG_TEMPLATE_ASIZE = 0  # swDwgTemplateAsize
SW_DWG_TEMPLATE_ASIZE_VERTICAL = 1  # swDwgTemplateAsizeVertical
SW_DWG_TEMPLATE_BSIZE = 2  # swDwgTemplateBsize
SW_DWG_TEMPLATE_CSIZE = 3  # swDwgTemplateCsize
SW_DWG_TEMPLATE_DSIZE = 4  # swDwgTemplateDsize
SW_DWG_TEMPLATE_ESIZE = 5  # swDwgTemplateEsize
SW_DWG_TEMPLATE_A4SIZE = 6  # swDwgTemplateA4size
SW_DWG_TEMPLATE_A4SIZE_VERTICAL = 7  # swDwgTemplateA4sizeVertical
SW_DWG_TEMPLATE_A3SIZE = 8  # swDwgTemplateA3size
SW_DWG_TEMPLATE_A2SIZE = 9  # swDwgTemplateA2size
SW_DWG_TEMPLATE_A1SIZE = 10  # swDwgTemplateA1size
SW_DWG_TEMPLATE_A0SIZE = 11  # swDwgTemplateA0size
SW_DWG_TEMPLATE_CUSTOM = 12  # swDwgTemplateCustom
SW_DWG_TEMPLATE_NONE = 13  # swDwgTemplateNone

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

# swExportDataFileType_e: Export data file types.
SW_EXPORT_PDF_DATA = 1  # swExportPdfData

# swExportDataSheetsToExport_e: Export data sheets to export options.
SW_EXPORT_DATA_EXPORT_ALL_SHEETS = 1  # swExportData_ExportAllSheets
SW_EXPORT_DATA_EXPORT_CURRENT_SHEET = 2  # swExportData_ExportCurrentSheet
SW_EXPORT_DATA_EXPORT_SPECIFIED_SHEETS = 3  # swExportData_ExportSpecifiedSheets

# swExportToDWG_e: Options for the Action parameter of IPartDoc::ExportToDWG2.
SW_EXPORT_TO_DWG_EXPORT_SHEET_METAL = 1  # swExportToDWG_ExportSheetMetal
SW_EXPORT_TO_DWG_EXPORT_SELECTED_FACES_OR_LOOPS = (
    2  # swExportToDWG_ExportSelectedFacesOrLoops
)
SW_EXPORT_TO_DWG_EXPORT_ANNOTATION_VIEWS = 3  # swExportToDWG_ExportAnnotationViews

# swFeatureChamferOption_e: Chamfer feature options. Bitmask.
SW_FEATURE_CHAMFER_FLIP_DIRECTION = 1  # swFeatureChamferFlipDirection
SW_FEATURE_CHAMFER_KEEP_FEATURE = 2  # swFeatureChamferKeepFeature
SW_FEATURE_CHAMFER_TANGENT_PROPAGATION = 4  # swFeatureChamferTangentPropagation
SW_FEATURE_CHAMFER_PROPAGATE_FEAT_TO_PARTS = 8  # swFeatureChamferPropagateFeatToParts

# swFeatureNameID_e: Feature name IDs.
SW_FM_AEM3DCONTACT = 3  # swFmAEM3DContact

# swFeatureScope_e: Feature scope options.
SW_FEATURE_SCOPE_ALL_BODIES = 0  # swFeatureScope_AllBodies -- All of the bodies in the multibody part are affected by the Mirror feature.
SW_FEATURE_SCOPE_SELECTED_BODIES_WITH_AUTO_SELECT = 1  # swFeatureScope_SelectedBodiesWithAutoSelect -- Only the specified bodies in the multibody part are affected by the Mirror feature when AutoSelect is true.
SW_FEATURE_SCOPE_SELECTED_BODIES_WITH_OUT_AUTO_SELECT = 2  # swFeatureScope_SelectedBodiesWithOutAutoSelect -- Only the specified bodies in the multibody part are affected by the Mirror feature when AutoSelect is false.

# swFileSaveError_e: File save errors. Bitmask.
SW_GENERIC_SAVE_ERROR = 1  # swGenericSaveError
SW_READ_ONLY_SAVE_ERROR = 2  # swReadOnlySaveError
SW_FILE_NAME_EMPTY = 4  # swFileNameEmpty
SW_FILE_NAME_CONTAINS_AT_SIGN = 8  # swFileNameContainsAtSign
SW_FILE_LOCK_ERROR = 16  # swFileLockError
SW_FILE_SAVE_FORMAT_NOT_AVAILABLE = 32  # swFileSaveFormatNotAvailable
SW_FILE_SAVE_AS_DO_NOT_OVERWRITE = 128  # swFileSaveAsDoNotOverwrite
SW_FILE_SAVE_AS_INVALID_FILE_EXTENSION = 256  # swFileSaveAsInvalidFileExtension
SW_FILE_SAVE_AS_BAD_EDRAWINGS_VERSION = 1024  # swFileSaveAsBadEDrawingsVersion
SW_FILE_SAVE_AS_NAME_EXCEEDS_MAX_PATH_LENGTH = (
    2048  # swFileSaveAsNameExceedsMaxPathLength
)
SW_FILE_SAVE_REQUIRES_SAVING_REFERENCES = 8192  # swFileSaveRequiresSavingReferences
SW_FILE_SAVE_AS_DETACHED_DRAWINGS_NOT_SUPPORTED = (
    16384  # swFileSaveAsDetachedDrawingsNotSupported
)

# swHingeMateEntityType_e: Hinge mate entity types.
SW_HINGE_MATE_ENTITY_TYPE_CONCENTRIC = 0  # swHingeMateEntityType_Concentric -- Select two concentric entities; valid selections are the same as for concentric mates
SW_HINGE_MATE_ENTITY_TYPE_ANGLE = 2  # swHingeMateEntityType_Angle -- Select two faces to define the extent of angular rotation

# swMateType_e: Assembly mate types.
SW_MATE_COINCIDENT = 0  # swMateCOINCIDENT
SW_MATE_CONCENTRIC = 1  # swMateCONCENTRIC
SW_MATE_PERPENDICULAR = 2  # swMatePERPENDICULAR
SW_MATE_PARALLEL = 3  # swMatePARALLEL
SW_MATE_TANGENT = 4  # swMateTANGENT
SW_MATE_DISTANCE = 5  # swMateDISTANCE
SW_MATE_ANGLE = 6  # swMateANGLE
SW_MATE_UNKNOWN = 7  # swMateUNKNOWN
SW_MATE_SYMMETRIC = 8  # swMateSYMMETRIC
SW_MATE_CAMFOLLOWER = 9  # swMateCAMFOLLOWER
SW_MATE_GEAR = 10  # swMateGEAR
SW_MATE_WIDTH = 11  # swMateWIDTH
SW_MATE_LOCKTOSKETCH = 12  # swMateLOCKTOSKETCH
SW_MATE_RACKPINION = 13  # swMateRACKPINION
SW_MATE_MAXMATES = 14  # swMateMAXMATES
SW_MATE_PATH = 15  # swMatePATH
SW_MATE_LOCK = 16  # swMateLOCK
SW_MATE_SCREW = 17  # swMateSCREW
SW_MATE_LINEARCOUPLER = 18  # swMateLINEARCOUPLER
SW_MATE_UNIVERSALJOINT = 19  # swMateUNIVERSALJOINT
SW_MATE_COORDINATE = 20  # swMateCOORDINATE
SW_MATE_SLOT = 21  # swMateSLOT
SW_MATE_HINGE = 22  # swMateHINGE
SW_MATE_SLIDER = 23  # swMateSLIDER
SW_MATE_PROFILECENTER = 24  # swMatePROFILECENTER
SW_MATE_MAGNETIC = 25  # swMateMAGNETIC

# swPersistReferencedObjectStates_e: Object codes for objects' persistent reference IDs. Bitmask.
SW_PERSIST_REFERENCED_OBJECT_OK = 0  # swPersistReferencedObject_Ok
SW_PERSIST_REFERENCED_OBJECT_INVALID = 1  # swPersistReferencedObject_Invalid
SW_PERSIST_REFERENCED_OBJECT_SUPPRESSED = 2  # swPersistReferencedObject_Suppressed
SW_PERSIST_REFERENCED_OBJECT_DELETED = 4  # swPersistReferencedObject_Deleted

# swRackPinionMateDistanceOptions_e: Rack and pinion mate distance options.
SW_PINION_PITCH_DIAMETER = (
    0  # swPinionPitchDiameter -- Specify the pinion pitch diameter
)
SW_RACK_TRAVEL_PER_REVOLUTION = 1  # swRackTravelPerRevolution -- Specify the distance the rack travels for each full rotation of the pinion

# swRefPlaneReferenceConstraints_e: Reference plane constraints. Bitmask.
SW_REF_PLANE_REFERENCE_CONSTRAINT_PARALLEL = 1  # swRefPlaneReferenceConstraint_Parallel
SW_REF_PLANE_REFERENCE_CONSTRAINT_PERPENDICULAR = (
    2  # swRefPlaneReferenceConstraint_Perpendicular
)
SW_REF_PLANE_REFERENCE_CONSTRAINT_COINCIDENT = (
    4  # swRefPlaneReferenceConstraint_Coincident
)
SW_REF_PLANE_REFERENCE_CONSTRAINT_DISTANCE = 8  # swRefPlaneReferenceConstraint_Distance
SW_REF_PLANE_REFERENCE_CONSTRAINT_ANGLE = 16  # swRefPlaneReferenceConstraint_Angle
SW_REF_PLANE_REFERENCE_CONSTRAINT_TANGENT = 32  # swRefPlaneReferenceConstraint_Tangent
SW_REF_PLANE_REFERENCE_CONSTRAINT_PROJECT = 64  # swRefPlaneReferenceConstraint_Project
SW_REF_PLANE_REFERENCE_CONSTRAINT_MID_PLANE = (
    128  # swRefPlaneReferenceConstraint_MidPlane
)
SW_REF_PLANE_REFERENCE_CONSTRAINT_OPTION_FLIP = (
    256  # swRefPlaneReferenceConstraint_OptionFlip
)
SW_REF_PLANE_REFERENCE_CONSTRAINT_OPTION_ORIGIN_ON_CURVE = (
    512  # swRefPlaneReferenceConstraint_OptionOriginOnCurve
)
SW_REF_PLANE_REFERENCE_CONSTRAINT_OPTION_PROJECT_TO_NEAREST_LOCATION = (
    1028  # swRefPlaneReferenceConstraint_OptionProjectToNearestLocation
)
SW_REF_PLANE_REFERENCE_CONSTRAINT_OPTION_PROJECT_ALONG_SKETCH_NORMAL = (
    2056  # swRefPlaneReferenceConstraint_OptionProjectAlongSketchNormal
)
SW_REF_PLANE_REFERENCE_CONSTRAINT_PARALLEL_TO_SCREEN = (
    4096  # swRefPlaneReferenceConstraint_ParallelToScreen
)
SW_REF_PLANE_REFERENCE_CONSTRAINT_OPTION_REFERENCE_FLIP = (
    8192  # swRefPlaneReferenceConstraint_OptionReferenceFlip
)

# swSaveAsOptions_e: Save As options. Bitmask.
SW_SAVE_AS_OPTIONS_SILENT = 1  # swSaveAsOptions_Silent
SW_SAVE_AS_OPTIONS_COPY = 2  # swSaveAsOptions_Copy
SW_SAVE_AS_OPTIONS_SAVE_REFERENCED = 4  # swSaveAsOptions_SaveReferenced
SW_SAVE_AS_OPTIONS_AVOID_REBUILD_ON_SAVE = 8  # swSaveAsOptions_AvoidRebuildOnSave
SW_SAVE_AS_OPTIONS_IGNORE_BIOGRAPHY = 256  # swSaveAsOptions_IgnoreBiography
SW_SAVE_AS_OPTIONS_COPY_AND_OPEN = 512  # swSaveAsOptions_CopyAndOpen
SW_SAVE_AS_OPTIONS_INCLUDE_VIRTUAL_SUB_ASM_COMPS = (
    1024  # swSaveAsOptions_IncludeVirtualSubAsmComps
)
SW_SAVE_AS_OPTIONS_EXPORT_TO2DPDF_FROM_INSPECTION = (
    2048  # swSaveAsOptions_ExportTo2DPdfFromInspection
)

# swSaveAsVersion_e: Version of a particular format to save the document.
SW_SAVE_AS_CURRENT_VERSION = (
    0  # swSaveAsCurrentVersion -- This is the typical save behavior.
)
SW_SAVE_AS_FORMAT_PRO_E = 2  # swSaveAsFormatProE
SW_SAVE_AS_STANDARD_DRAWING = 3  # swSaveAsStandardDrawing
SW_SAVE_AS_DETACHED_DRAWING = 4  # swSaveAsDetachedDrawing

# swSelectType_e: Values for types of returned IDs.

# swSelectionMarkAction_e: Selecton mark actions.
SW_SELECTION_MARK_SET = 0  # swSelectionMarkSet
SW_SELECTION_MARK_APPEND = 1  # swSelectionMarkAppend
SW_SELECTION_MARK_REMOVE = 2  # swSelectionMarkRemove
SW_SELECTION_MARK_CLEAR = 3  # swSelectionMarkClear

# swSimpleFilletType_e: Simple fillet types.
SW_CONST_RADIUS_FILLET = 0  # swConstRadiusFillet
SW_FACE_FILLET = 2  # swFaceFillet
SW_FULL_ROUND_FILLET = 3  # swFullRoundFillet

# swSlotMateConstraintOptions_e: Slot mate constraint options.
SW_SLOT_MATE_CONSTRAINT_OPTION_FREE = 0  # swSlotMateConstraintOption_Free -- Allow the component to move freely in the slot
SW_SLOT_MATE_CONSTRAINT_OPTION_CENTERED = (
    1  # swSlotMateConstraintOption_Centered -- Center the component in the slot
)
SW_SLOT_MATE_CONSTRAINT_OPTION_DISTANCE = 2  # swSlotMateConstraintOption_Distance -- Place the component axis at a specified distance from the end of the slot
SW_SLOT_MATE_CONSTRAINT_OPTION_PERCENT = 3  # swSlotMateConstraintOption_Percent -- Place the component axis at a specified percent of slot length distance from the end of the slot

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

# swTolType_e: Dimension tolerance types.
SW_TOL_NONE = 0  # swTolNONE
SW_TOL_BASIC = 1  # swTolBASIC
SW_TOL_BILAT = 2  # swTolBILAT
SW_TOL_LIMIT = 3  # swTolLIMIT
SW_TOL_SYMMETRIC = 4  # swTolSYMMETRIC
SW_TOL_MIN = 5  # swTolMIN
SW_TOL_MAX = 6  # swTolMAX
SW_TOL_FIT = 7  # swTolFIT
SW_TOL_METRIC = 7  # swTolMETRIC
SW_TOL_FITWITHTOL = 8  # swTolFITWITHTOL
SW_TOL_FITTOLONLY = 9  # swTolFITTOLONLY
SW_TOL_BLOCK = 10  # swTolBLOCK
SW_TOL_GENERAL = 11  # swTolGeneral

# swUserPreferenceIntegerValue_e: User-preference enumerators for system options and document properties.

# swUserPreferenceToggle_e: User-preference enumerators for system options and document properties.

# swWzdGeneralHoleTypes_e: General Hole Wizard types.
SW_WZD_COUNTER_BORE = 0  # swWzdCounterBore
SW_WZD_COUNTER_SINK = 1  # swWzdCounterSink
SW_WZD_HOLE = 2  # swWzdHole
SW_WZD_PIPE_TAP = 3  # swWzdPipeTap -- Tapered tap hole
SW_WZD_TAP = 4  # swWzdTap -- Pipe/straight tap hole
SW_WZD_LEGACY = 5  # swWzdLegacy
SW_WZD_COUNTER_BORE_SLOT = 6  # swWzdCounterBoreSlot
SW_WZD_COUNTER_SINK_SLOT = 7  # swWzdCounterSinkSlot
SW_WZD_HOLE_SLOT = 8  # swWzdHoleSlot

# -----------------------------------------------------------------------------
# Method signatures (for arg-count validation)
# -----------------------------------------------------------------------------

METHOD_SIGNATURES: dict[str, dict[str, object]] = {
    "IAnnotation.GetType": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.int",
        "summary": "Gets the type of the annotation.",
    },
    "IAssemblyDoc.AddComponent4": {
        "args_count": 5,
        "arg_names": ["CompName", "ConfigName", "X", "Y", "Z"],
        "arg_types": [
            "system.string",
            "system.string",
            "system.double",
            "system.double",
            "system.double",
        ],
        "return_type": "Component2",
        "summary": "Obsolete. Superseded by IAssemblyDoc::AddComponent5.",
    },
    "IAssemblyDoc.CreateExplodedView": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.bool",
        "summary": "Creates an explode view of the active assembly configuration.",
    },
    "IAssemblyDoc.CreateMate": {
        "args_count": 1,
        "arg_names": ["MateData"],
        "arg_types": ["system.object"],
        "return_type": "System.object",
        "summary": "Creates a mate with the specified feature data object.",
    },
    "IAssemblyDoc.CreateMateData": {
        "args_count": 1,
        "arg_names": ["Type"],
        "arg_types": ["system.int"],
        "return_type": "System.object",
        "summary": "Creates a mate feature data object for the specified mate type.",
    },
    "IAssemblyDoc.GetComponents": {
        "args_count": 1,
        "arg_names": ["ToplevelOnly"],
        "arg_types": ["system.bool"],
        "return_type": "System.object",
        "summary": "Gets all of the components in the active configuration of this assembly.",
    },
    "IAssemblyDoc.MirrorComponents": {
        "args_count": 9,
        "arg_names": [
            "Plane",
            "ComponentsToInstance",
            "ComponentsToMirror",
            "MirroredComponentFilenames",
            "RecreateMates",
            "ComponentModifier",
            "ComponentNameModifier",
            "MirroredFileLocation",
            "CopyCustomProperties",
        ],
        "arg_types": [
            "system.object",
            "system.object",
            "system.object",
            "system.object",
            "system.bool",
            "system.int",
            "system.string",
            "system.string",
            "system.bool",
        ],
        "return_type": "System.object",
        "summary": "Obsolete. Superseded by IAssemblyDoc::MirrorComponents2.",
    },
    "IBody.GetMassProperties": {
        "args_count": 1,
        "arg_names": ["Density"],
        "arg_types": ["system.double"],
        "return_type": "System.object",
        "summary": "Obsolete. Superseded by IBody2::GetMassProperties.",
    },
    "IBody2.GetEdges": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the edges for this body.",
    },
    "IBody2.GetFaces": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets all of the faces on the body.",
    },
    "IBody2.GetMassProperties": {
        "args_count": 1,
        "arg_names": ["Density"],
        "arg_types": ["system.double"],
        "return_type": "System.object",
        "summary": "Gets the mass properties of this body.",
    },
    "IBomTableAnnotation.GetComponentsCount2": {
        "args_count": 4,
        "arg_names": ["RowIndex", "Configuration", "ItemNumber", "PartNumber"],
        "arg_types": ["system.int", "system.string", "system.string", "system.string"],
        "return_type": "System.int",
        "summary": "Gets the number of components, the item number, and the part number in the specified row for the specified configuration in this BOM table annotation.",
    },
    "IComponent2.GetBodies": {
        "args_count": 1,
        "arg_names": ["BodyType"],
        "arg_types": ["system.int"],
        "return_type": "System.object",
        "summary": "Obsolete. Superseded by IComponent2::GetBodies2.",
    },
    "IComponent2.GetModelDoc2": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the model document for this component.",
    },
    "IComponent2.GetSelectByIDString": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.string",
        "summary": "Gets the name of the component for possible use with IModelDocExtension::SelectByID2, for selectively opening a document using ISldWorks::OpenDoc7 and IDocumentSpecification, etc.",
    },
    "IComponent2.GetSuppression2": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.int",
        "summary": "Gets the suppression state of this component.",
    },
    "IComponent2.Select2": {
        "args_count": 2,
        "arg_names": ["Append", "Mark"],
        "arg_types": ["system.bool", "system.int"],
        "return_type": "System.bool",
        "summary": "Obsolete. Superseded by IComponent2::Select3.",
    },
    "IComponent2.SetTransformAndSolve": {
        "args_count": 1,
        "arg_names": ["XformIn"],
        "arg_types": ["mathtransform"],
        "return_type": "System.bool",
        "summary": "Obsolete. Superseded by IComponent2::SetTransformAndSolve2.",
    },
    "IConfiguration.AddExplodeStep": {
        "args_count": 4,
        "arg_names": ["ExplDist", "ReverseDir", "RigidSubassembly", "ExplodeRelated"],
        "arg_types": ["system.double", "system.bool", "system.bool", "system.bool"],
        "return_type": "System.object",
        "summary": "Obsolete. Superseded by IConfiguration::AddExplodeStep2.",
    },
    "IConfigurationManager.AddConfiguration2": {
        "args_count": 7,
        "arg_names": [
            "Name",
            "Comment",
            "AlternateName",
            "Options",
            "ParentConfigName",
            "Description",
            "Rebuild",
        ],
        "arg_types": [
            "system.string",
            "system.string",
            "system.string",
            "system.int",
            "system.string",
            "system.string",
            "system.bool",
        ],
        "return_type": "Configuration",
        "summary": "Creates a new configuration.",
    },
    "ICurve.Evaluate": {
        "args_count": 1,
        "arg_names": ["Parameter"],
        "arg_types": ["system.double"],
        "return_type": "System.object",
        "summary": "Obsolete. Superseded by ICurve::Evaluate2.",
    },
    "ICurve.GetEndParams": {
        "args_count": 4,
        "arg_names": ["Start", "End", "IsClosed", "IsPeriodic"],
        "arg_types": ["system.double", "system.double", "system.bool", "system.bool"],
        "return_type": "System.bool",
        "summary": "Gets the end conditions of this curve.",
    },
    "ICurve.GetLength": {
        "args_count": 2,
        "arg_names": ["StartParam", "EndParam"],
        "arg_types": ["system.double", "system.double"],
        "return_type": "System.double",
        "summary": "Obsolete. Superseded by ICurve::GetLength2.",
    },
    "ICurve.IsLine": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.bool",
        "summary": "Gets whether the curve is a line.",
    },
    "ICustomPropertyManager.Add3": {
        "args_count": 4,
        "arg_names": ["FieldName", "FieldType", "FieldValue", "OverwriteExisting"],
        "arg_types": ["system.string", "system.int", "system.string", "system.int"],
        "return_type": "System.int",
        "summary": "Adds a custom property to a configuration or model document.",
    },
    "ICustomPropertyManager.Count": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": None,
        "summary": "Gets the number of custom properties.",
    },
    "ICustomPropertyManager.Get4": {
        "args_count": 4,
        "arg_names": ["FieldName", "UseCached", "ValOut", "ResolvedValOut"],
        "arg_types": ["system.string", "system.bool", "system.string", "system.string"],
        "return_type": "System.bool",
        "summary": "Obsolete. Superseded by ICustomPropertyManager::Get5.",
    },
    "ICustomPropertyManager.GetNames": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the names of the custom properties.",
    },
    "IDesignTable.Attach": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.bool",
        "summary": "Activates the design table within the part or assembly document.",
    },
    "IDesignTable.Detach": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "void",
        "summary": "Detaches the design table from the Microsoft Excel sheet.",
    },
    "IDesignTable.EditTable2": {
        "args_count": 1,
        "arg_names": ["NewWindow"],
        "arg_types": ["system.bool"],
        "return_type": "System.object",
        "summary": "Lets you edit the design table.",
    },
    "IDesignTable.UpdateModel": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.bool",
        "summary": "Applies the edits to the design table to the model.",
    },
    "IDesignTable.UpdateTable": {
        "args_count": 2,
        "arg_names": ["Type", "Close"],
        "arg_types": ["system.int", "system.bool"],
        "return_type": "System.bool",
        "summary": "Applies the changes made to the design table to the model.",
    },
    "IDesignTable.Worksheet": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": None,
        "summary": "Gets the Microsoft Excel worksheet for this design table.",
    },
    "IDimension.SetToleranceType": {
        "args_count": 1,
        "arg_names": ["NewType"],
        "arg_types": ["system.int"],
        "return_type": "System.bool",
        "summary": "Obsolete. Superseded by IDimensionTolerance::Type.",
    },
    "IDimension.SetToleranceValues": {
        "args_count": 2,
        "arg_names": ["TolMin", "TolMax"],
        "arg_types": ["system.double", "system.double"],
        "return_type": "System.bool",
        "summary": "Obsolete. Superseded by IDimensionTolerance::SetValues.",
    },
    "IDisplayDimension.GetDimension2": {
        "args_count": 1,
        "arg_names": ["Index"],
        "arg_types": ["system.int"],
        "return_type": "Dimension",
        "summary": "Gets the model dimension used to create this display dimension.",
    },
    "IDrawingDoc.ActivateSheet": {
        "args_count": 1,
        "arg_names": ["Name"],
        "arg_types": ["system.string"],
        "return_type": "System.bool",
        "summary": "Activates the specified drawing sheet.",
    },
    "IDrawingDoc.ActivateView": {
        "args_count": 1,
        "arg_names": ["ViewName"],
        "arg_types": ["system.string"],
        "return_type": "System.bool",
        "summary": "Activates the specified drawing view.",
    },
    "IDrawingDoc.CreateDetailViewAt4": {
        "args_count": 12,
        "arg_names": [
            "X",
            "Y",
            "Z",
            "Style",
            "Scale1",
            "Scale2",
            "LabelIn",
            "Showtype",
            "FullOutline",
            "JaggedOutline",
            "NoOutline",
            "ShapeIntensity",
        ],
        "arg_types": [
            "system.double",
            "system.double",
            "system.double",
            "system.int",
            "system.double",
            "system.double",
            "system.string",
            "system.int",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.int",
        ],
        "return_type": "System.object",
        "summary": "Creates a detail view in a drawing document.",
    },
    "IDrawingDoc.CreateDrawViewFromModelView3": {
        "args_count": 5,
        "arg_names": ["ModelName", "ViewName", "LocX", "LocY", "LocZ"],
        "arg_types": [
            "system.string",
            "system.string",
            "system.double",
            "system.double",
            "system.double",
        ],
        "return_type": "View",
        "summary": "Creates a drawing view on the current drawing sheet using the specified model view.",
    },
    "IDrawingDoc.CreateFlatPatternViewFromModelView3": {
        "args_count": 7,
        "arg_names": [
            "ModelName",
            "ConfigName",
            "LocX",
            "LocY",
            "LocZ",
            "HideBendLines",
            "FlipView",
        ],
        "arg_types": [
            "system.string",
            "system.string",
            "system.double",
            "system.double",
            "system.double",
            "system.bool",
            "system.bool",
        ],
        "return_type": "View",
        "summary": "Creates a flat-pattern view from a model view.",
    },
    "IDrawingDoc.CreateSectionViewAt5": {
        "args_count": 7,
        "arg_names": [
            "X",
            "Y",
            "Z",
            "SectionLabel",
            "Options",
            "ExcludedComponents",
            "SectionDepth",
        ],
        "arg_types": [
            "system.double",
            "system.double",
            "system.double",
            "system.string",
            "system.int",
            "system.object",
            "system.double",
        ],
        "return_type": "View",
        "summary": "Creates the specified section view.",
    },
    "IDrawingDoc.GetCurrentSheet": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the currently active drawing sheet.",
    },
    "IDrawingDoc.GetSheetNames": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets a list of the names of the drawing sheets in this drawing.",
    },
    "IDrawingDoc.InsertModelAnnotations3": {
        "args_count": 6,
        "arg_names": [
            "Option",
            "Types",
            "AllViews",
            "DuplicateDims",
            "HiddenFeatureDims",
            "UsePlacementInSketch",
        ],
        "arg_types": [
            "system.int",
            "system.int",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.bool",
        ],
        "return_type": "System.object",
        "summary": "Inserts model annotations into this drawing document's currently selected drawing view.",
    },
    "IDrawingDoc.NewSheet3": {
        "args_count": 10,
        "arg_names": [
            "Name",
            "PaperSize",
            "TemplateIn",
            "Scale1",
            "Scale2",
            "FirstAngle",
            "TemplateName",
            "Width",
            "Height",
            "PropertyViewName",
        ],
        "arg_types": [
            "system.string",
            "system.int",
            "system.int",
            "system.double",
            "system.double",
            "system.bool",
            "system.string",
            "system.double",
            "system.double",
            "system.string",
        ],
        "return_type": "System.bool",
        "summary": "Obsolete. Superseded by IDrawingDoc::NewSheet4.",
    },
    "IEdge.GetClosestPointOn": {
        "args_count": 3,
        "arg_names": ["X", "Y", "Z"],
        "arg_types": ["system.double", "system.double", "system.double"],
        "return_type": "System.object",
        "summary": "Uses the X,Y,Z input point and returns the closest point on the edge.",
    },
    "IEdge.GetCurve": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the underlying curve for this edge.",
    },
    "IEdge.GetStartVertex": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the starting vertex for this edge.",
    },
    "IEntity.Select2": {
        "args_count": 2,
        "arg_names": ["Append", "Mark"],
        "arg_types": ["system.bool", "system.int"],
        "return_type": "System.bool",
        "summary": "Obsolete. Superseded by IEntity::Select4.",
    },
    "IEntity.Select4": {
        "args_count": 2,
        "arg_names": ["Append", "Data"],
        "arg_types": ["system.bool", "selectdata"],
        "return_type": "System.bool",
        "summary": "Selects an entity and marks it.",
    },
    "IEquationMgr.Add2": {
        "args_count": 3,
        "arg_names": ["Index", "Equation", "Solve"],
        "arg_types": ["system.int", "system.string", "system.bool"],
        "return_type": "System.int",
        "summary": "Adds an equation at the specified index.",
    },
    "IEquationMgr.Equation": {
        "args_count": 1,
        "arg_names": ["Index"],
        "arg_types": ["system.int"],
        "return_type": "System.string",
        "summary": "Gets or sets the equation at the specified index.",
    },
    "IEquationMgr.GlobalVariable": {
        "args_count": 1,
        "arg_names": ["Index"],
        "arg_types": ["system.int"],
        "return_type": "System.bool",
        "summary": "Gets whether the equation at the specified index is a global variable.",
    },
    "IEquationMgr.Suppression": {
        "args_count": 1,
        "arg_names": ["Index"],
        "arg_types": ["system.int"],
        "return_type": "System.bool",
        "summary": "Obsolete as of SOLIDWORKS 2014 and later.",
    },
    "IEquationMgr.Value": {
        "args_count": 1,
        "arg_names": ["Index"],
        "arg_types": ["system.int"],
        "return_type": "System.double",
        "summary": "Gets the value of the equation at the specified index.",
    },
    "IExportPdfData.SetSheets": {
        "args_count": 2,
        "arg_names": ["Which", "Sheets"],
        "arg_types": ["system.int", "system.object"],
        "return_type": "System.bool",
        "summary": "Sets the drawing sheets to export.",
    },
    "IFace.GetClosestPointOn": {
        "args_count": 3,
        "arg_names": ["X", "Y", "Z"],
        "arg_types": ["system.double", "system.double", "system.double"],
        "return_type": "System.object",
        "summary": "Obsolete. Superseded by IFace2:: GetClosestPointOn.",
    },
    "IFace.GetSurface": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Obsolete. Superseded by IFace2::GetSurface.",
    },
    "IFace2.GetArea": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.double",
        "summary": "Gets the area of this face.",
    },
    "IFace2.GetClosestPointOn": {
        "args_count": 3,
        "arg_names": ["X", "Y", "Z"],
        "arg_types": ["system.double", "system.double", "system.double"],
        "return_type": "System.object",
        "summary": "Uses the X,Y,Z input point to determine the closest point on the face.",
    },
    "IFace2.GetSurface": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the surface referenced by this face.",
    },
    "IFeature.GetBody": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Obsolete. Superseded by IFeatures::GetFaces, IFeatures::IGetFaces2, IFace2::GetBody, and IFace2::IGetBody.",
    },
    "IFeature.GetDefinition": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the feature data object for a feature, such as an advanced mate, extrusion, loft, fillet, chamfer, etc., in order to access the parameters that control the definition of this feature.",
    },
    "IFeature.GetErrorCode": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.int",
        "summary": "Obsolete. Superseded by IFeature::GetErrorCode2.",
    },
    "IFeature.GetErrorCode2": {
        "args_count": 1,
        "arg_names": ["IsWarning"],
        "arg_types": ["system.bool"],
        "return_type": "System.int",
        "summary": "Gets the error code for this feature.",
    },
    "IFeature.GetFaces": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the faces in this feature.",
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
    "IFeature.GetTypeName2": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.string",
        "summary": 'Gets the type of feature. NOTE: To get the underlying type of feature of an Instant3D feature (i.e., "ICE"), call IFeature::GetTypeName; otherwise, call this method.',
    },
    "IFeature.IsSuppressed": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.bool",
        "summary": "Obsolete. Superseded by IFeature::IsSuppressed2.",
    },
    "IFeature.IsSuppressed2": {
        "args_count": 2,
        "arg_names": ["Config_opt", "Config_names"],
        "arg_types": ["system.int", "system.object"],
        "return_type": "System.object",
        "summary": "Gets whether the feature in the specified configurations is suppressed.",
    },
    "IFeature.Select2": {
        "args_count": 2,
        "arg_names": ["Append", "Mark"],
        "arg_types": ["system.bool", "system.int"],
        "return_type": "System.bool",
        "summary": "Selects and marks this feature.",
    },
    "IFeature.SetSuppression": {
        "args_count": 1,
        "arg_names": ["SuppressState"],
        "arg_types": ["system.int"],
        "return_type": "System.bool",
        "summary": "Obsolete. Superseded by IFeature::SetSuppression2.",
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
    "IFeatureManager.GetFeatures": {
        "args_count": 1,
        "arg_names": ["ToplevelOnly"],
        "arg_types": ["system.bool"],
        "return_type": "System.object",
        "summary": "Gets the features in this document.",
    },
    "IFeatureManager.InsertCombineFeature": {
        "args_count": 3,
        "arg_names": ["OperationType", "MainBody", "ToolVar"],
        "arg_types": ["system.int", "body2", "system.object"],
        "return_type": "Feature",
        "summary": "Combines the specified bodies in the multibody part to create a combine feature.",
    },
    "IFeatureManager.InsertCoordinateSystem": {
        "args_count": 3,
        "arg_names": ["XFlippedIn", "YFlippedIn", "ZFlippedIn"],
        "arg_types": ["system.bool", "system.bool", "system.bool"],
        "return_type": "Feature",
        "summary": "Inserts a coordinate system feature.",
    },
    "IFeatureManager.InsertDeleteBody2": {
        "args_count": 1,
        "arg_names": ["KeepBodies"],
        "arg_types": ["system.bool"],
        "return_type": "Feature",
        "summary": "Inserts a Body-Delete/Keep feature.",
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
    "IFeatureManager.InsertMultiFaceDraft": {
        "args_count": 6,
        "arg_names": [
            "Angle",
            "FlipDir",
            "EdgeDraft",
            "PropType",
            "IsStepDraft",
            "IsBodyDraft",
        ],
        "arg_types": [
            "system.double",
            "system.bool",
            "system.bool",
            "system.int",
            "system.bool",
            "system.bool",
        ],
        "return_type": "Feature",
        "summary": "Inserts a multiface draft feature.",
    },
    "IFeatureManager.InsertRefPlane": {
        "args_count": 6,
        "arg_names": [
            "FirstConstraint",
            "FirstConstraintAngleOrDistance",
            "SecondConstraint",
            "SecondConstraintAngleOrDistance",
            "ThirdConstraint",
            "ThirdConstraintAngleOrDistance",
        ],
        "arg_types": [
            "system.int",
            "system.double",
            "system.int",
            "system.double",
            "system.int",
            "system.double",
        ],
        "return_type": "System.object",
        "summary": "Inserts a constraint-based reference plane using the selected reference entities.",
    },
    "IFeatureManager.InsertReferencePoint": {
        "args_count": 4,
        "arg_names": [
            "NRefPointType",
            "NRefPointAlongCurveType",
            "DDistance_or_Percent",
            "NumberOfRefPoints",
        ],
        "arg_types": ["system.int", "system.int", "system.double", "system.int"],
        "return_type": "System.object",
        "summary": "Creates the geometry for the reference points based on any of these selected entities: edges, faces, planes, vertices, or sketch geometry.",
    },
    "IFeatureManager.InsertRib": {
        "args_count": 10,
        "arg_names": [
            "Is2Sided",
            "ReverseThicknessDir",
            "Thickness",
            "ReferenceEdgeIndex",
            "ReverseMaterialDir",
            "IsDrafted",
            "DraftOutward",
            "DraftAngle",
            "IsNormToSketch",
            "IsDraftedFromWall",
        ],
        "arg_types": [
            "system.bool",
            "system.bool",
            "system.double",
            "system.int",
            "system.bool",
            "system.bool",
            "system.bool",
            "system.double",
            "system.bool",
            "system.bool",
        ],
        "return_type": "void",
        "summary": "Inserts a rib.",
    },
    "IFeatureManager.InsertSheetMetalEdgeFlange2": {
        "args_count": 13,
        "arg_names": [
            "FlangeEdges",
            "SketchFeats",
            "BooleanOptions",
            "FlangeAngle",
            "FlangeRadius",
            "BendPosition",
            "FlangeOffsetDist",
            "ReliefType",
            "FlangeReliefRatio",
            "FlangeReliefWidth",
            "FlangeReliefDepth",
            "FlangeSharpType",
            "CustomBendAllowance",
        ],
        "arg_types": [
            "system.object",
            "system.object",
            "system.int",
            "system.double",
            "system.double",
            "system.int",
            "system.double",
            "system.int",
            "system.double",
            "system.double",
            "system.double",
            "system.int",
            "custombendallowance",
        ],
        "return_type": "Feature",
        "summary": "Obsolete. Superseded by IFeatureManager::CreateDefinition and IFeatureManager::CreateFeature.",
    },
    "IFeatureManager.InsertWrapFeature2": {
        "args_count": 5,
        "arg_names": ["Type", "Thickness", "ReverseDir", "Method", "MeshFactor"],
        "arg_types": [
            "system.int",
            "system.double",
            "system.bool",
            "system.int",
            "system.int",
        ],
        "return_type": "Feature",
        "summary": "Inserts a wrap feature.",
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
    "IHoleDataTable.GetCellData": {
        "args_count": 3,
        "arg_names": ["ColumnName", "RowIndex", "CellData"],
        "arg_types": ["system.string", "system.int", "system.string"],
        "return_type": "System.bool",
        "summary": "Gets data from the specified table cell of this Hole Wizard fastener table.",
    },
    "IHoleDataTable.GetColumnNames": {
        "args_count": 1,
        "arg_names": ["ColumnNames"],
        "arg_types": ["system.object"],
        "return_type": "System.bool",
        "summary": "Gets the names of all the columns in this Hole Wizard fastener table.",
    },
    "IHoleStandardsData.GetFastenerTable": {
        "args_count": 4,
        "arg_names": ["StandardName", "FastenerID", "TableID", "HoleTable"],
        "arg_types": ["system.string", "system.int", "system.int", "system.object"],
        "return_type": "System.bool",
        "summary": "Gets the Hole Wizard fastener table for the specified Hole Wizard standard, fastener ID, and fastener table type ID.",
    },
    "IHoleStandardsData.GetFastenerTableTypes": {
        "args_count": 3,
        "arg_names": ["StandardName", "FastenerID", "FastenerTableTypeIDs"],
        "arg_types": ["system.string", "system.int", "system.object"],
        "return_type": "System.bool",
        "summary": "Gets the array of three fastener table type IDs for the given fastener in the given Hole Wizard standard.",
    },
    "IHoleStandardsData.GetFastenerTypes": {
        "args_count": 3,
        "arg_names": ["StandardName", "FastenerIndexes", "FastenerNames"],
        "arg_types": ["system.string", "system.object", "system.object"],
        "return_type": "System.bool",
        "summary": "Gets the fasteners in the specified Hole Wizard standard.",
    },
    "IHoleStandardsData.GetHoleStandards": {
        "args_count": 2,
        "arg_names": ["Indexes", "Names"],
        "arg_types": ["system.object", "system.object"],
        "return_type": "System.bool",
        "summary": "Gets Hole Wizard standards.",
    },
    "IInterferenceDetectionMgr.Done": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "void",
        "summary": "Stops the interference detection.",
    },
    "IInterferenceDetectionMgr.GetInterferenceCount": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.int",
        "summary": "Calculates and gets the number of interferences.",
    },
    "IInterferenceDetectionMgr.GetInterferences": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Calculates and gets the interferences.",
    },
    "IMassProperty.GetMomentOfInertia": {
        "args_count": 1,
        "arg_names": ["WhereTaken"],
        "arg_types": ["system.int"],
        "return_type": "System.object",
        "summary": "Gets the moment of inertia at the specified coordinate system for this model.",
    },
    "IMassProperty2.GetMomentOfInertia": {
        "args_count": 1,
        "arg_names": ["WhereTaken"],
        "arg_types": ["system.int"],
        "return_type": "System.object",
        "summary": "Gets the moment of inertia at the specified coordinate system for the selected bodies/components.",
    },
    "IMathUtility.CreatePoint": {
        "args_count": 1,
        "arg_names": ["ArrayDataIn"],
        "arg_types": ["system.object"],
        "return_type": "System.object",
        "summary": "Creates a new math point.",
    },
    "IMathUtility.CreateTransform": {
        "args_count": 1,
        "arg_names": ["ArrayDataIn"],
        "arg_types": ["system.object"],
        "return_type": "System.object",
        "summary": "Creates a new math transform.",
    },
    "IMathUtility.CreateVector": {
        "args_count": 1,
        "arg_names": ["ArrayDataIn"],
        "arg_types": ["system.object"],
        "return_type": "System.object",
        "summary": "Creates a math vector.",
    },
    "IMeasure.Calculate": {
        "args_count": 1,
        "arg_names": ["Entities"],
        "arg_types": ["system.object"],
        "return_type": "System.bool",
        "summary": "Measures the selected or specified entities.",
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
    "IModelDoc2.EditSketch": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "void",
        "summary": "Allows the currently selected sketch to be edited.",
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
    "IModelDoc2.FeatureCut5": {
        "args_count": 19,
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
            "KeepPieceIndex",
            "NormalCut",
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
            "system.int",
            "system.bool",
        ],
        "return_type": "void",
        "summary": "Obsolete. Superseded by IFeatureManager::FeatureCut.",
    },
    "IModelDoc2.ForceRebuild3": {
        "args_count": 1,
        "arg_names": ["TopOnly"],
        "arg_types": ["system.bool"],
        "return_type": "System.bool",
        "summary": "Forces a rebuild of all features in the active configuration in the model.",
    },
    "IModelDoc2.GetActiveConfiguration": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Obsolete. Superseded by IConfigurationManager::ActiveConfiguration.",
    },
    "IModelDoc2.GetConfigurationNames": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the names of the configurations in this document.",
    },
    "IModelDoc2.GetDesignTable": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the design table associated with this part or assembly document.",
    },
    "IModelDoc2.GetFeatureCount": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.int",
        "summary": "Gets the number of features in this document.",
    },
    "IModelDoc2.GetTitle": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.string",
        "summary": "Gets the title of the document that appears in the active window's title bar.",
    },
    "IModelDoc2.GetType": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.int",
        "summary": "Gets the type of the document.",
    },
    "IModelDoc2.InsertAxis2": {
        "args_count": 1,
        "arg_names": ["AutoSize"],
        "arg_types": ["system.bool"],
        "return_type": "System.bool",
        "summary": "Inserts a reference axis based on the currently selected items with an option to automatically size the axis.",
    },
    "IModelDoc2.InsertDome": {
        "args_count": 3,
        "arg_names": ["Height", "ReverseDir", "DoEllipticSurface"],
        "arg_types": ["system.double", "system.bool", "system.bool"],
        "return_type": "void",
        "summary": "Inserts a dome.",
    },
    "IModelDoc2.InsertFamilyTableNew": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "void",
        "summary": "Inserts an existing design table from the model into the selected drawing view.",
    },
    "IModelDoc2.InsertFeatureShell": {
        "args_count": 2,
        "arg_names": ["Thickness", "Outward"],
        "arg_types": ["system.double", "system.bool"],
        "return_type": "void",
        "summary": "Creates a shell feature.",
    },
    "IModelDoc2.InsertSketch2": {
        "args_count": 1,
        "arg_names": ["UpdateEditRebuild"],
        "arg_types": ["system.bool"],
        "return_type": "void",
        "summary": "Obsolete. Superseded by ISketchManager::InsertSketch.",
    },
    "IModelDoc2.InsertSketchText": {
        "args_count": 9,
        "arg_names": [
            "Ptx",
            "Pty",
            "Ptz",
            "Text",
            "Alignment",
            "FlipDirection",
            "HorizontalMirror",
            "WidthFactor",
            "SpaceBetweenChars",
        ],
        "arg_types": [
            "system.double",
            "system.double",
            "system.double",
            "system.string",
            "system.int",
            "system.int",
            "system.int",
            "system.int",
            "system.int",
        ],
        "return_type": "System.object",
        "summary": "Inserts sketch text.",
    },
    "IModelDoc2.InsertSurfaceFinishSymbol2": {
        "args_count": 14,
        "arg_names": [
            "SymType",
            "LeaderType",
            "LocX",
            "LocY",
            "LocZ",
            "LaySymbol",
            "ArrowType",
            "MachAllowance",
            "OtherVals",
            "ProdMethod",
            "SampleLen",
            "MaxRoughness",
            "MinRoughness",
            "RoughnessSpacing",
        ],
        "arg_types": [
            "system.int",
            "system.int",
            "system.double",
            "system.double",
            "system.double",
            "system.int",
            "system.int",
            "system.string",
            "system.string",
            "system.string",
            "system.string",
            "system.string",
            "system.string",
            "system.string",
        ],
        "return_type": "System.bool",
        "summary": "Obsolete. Superseded by IModelDocExtension::InsertSurfaceFinishSymbol3.",
    },
    "IModelDoc2.Parameter": {
        "args_count": 1,
        "arg_names": ["StringIn"],
        "arg_types": ["system.string"],
        "return_type": "System.object",
        "summary": "Gets the specified parameter.",
    },
    "IModelDoc2.Save": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "void",
        "summary": "Obsolete. Superseded by IModelDoc2::Save3.",
    },
    "IModelDoc2.SaveAs3": {
        "args_count": 3,
        "arg_names": ["NewName", "SaveAsVersion", "Options"],
        "arg_types": ["system.string", "system.int", "system.int"],
        "return_type": "System.int",
        "summary": "Obsolete. Superseded by IModelDocExtension::SaveAs.",
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
    "IModelDoc2.ShowConfiguration2": {
        "args_count": 1,
        "arg_names": ["ConfigurationName"],
        "arg_types": ["system.string"],
        "return_type": "System.bool",
        "summary": "Shows the named configuration by switching to that configuration and making it the active configuration.",
    },
    "IModelDoc2.SketchAddConstraints": {
        "args_count": 1,
        "arg_names": ["IdStr"],
        "arg_types": ["system.string"],
        "return_type": "void",
        "summary": "Adds the specified constraint to the selected entities.",
    },
    "IModelDocExtension.CreateMassProperty": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "MassProperty",
        "summary": "Obsolete. Superseded by IModelDocExtension::CreateMassProperty2.",
    },
    "IModelDocExtension.CreateMeasure": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "Measure",
        "summary": "Creates a measure tool.",
    },
    "IModelDocExtension.CustomPropertyManager": {
        "args_count": 1,
        "arg_names": ["ConfigName"],
        "arg_types": ["system.string"],
        "return_type": "CustomPropertyManager",
        "summary": "Gets the custom properties for this document or configuration.",
    },
    "IModelDocExtension.GetObjectByPersistReference3": {
        "args_count": 2,
        "arg_names": ["PersistId", "ErrorCode"],
        "arg_types": ["system.object", "system.int"],
        "return_type": "System.object",
        "summary": "Gets the object assigned to the specified persistent reference ID.",
    },
    "IModelDocExtension.GetPersistReference3": {
        "args_count": 1,
        "arg_names": ["DispObj"],
        "arg_types": ["system.object"],
        "return_type": "System.object",
        "summary": "Gets the persistent reference ID for the specified object in this model document.",
    },
    "IModelDocExtension.SaveAs": {
        "args_count": 6,
        "arg_names": ["Name", "Version", "Options", "ExportData", "Errors", "Warnings"],
        "arg_types": [
            "system.string",
            "system.int",
            "system.int",
            "system.object",
            "system.int",
            "system.int",
        ],
        "return_type": "System.bool",
        "summary": "Obsolete. Superseded by IModelDocExtension::SaveAs2.",
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
    "IPartDoc.ExportFlatPatternView": {
        "args_count": 2,
        "arg_names": ["FilePath", "Options"],
        "arg_types": ["system.string", "system.int"],
        "return_type": "System.bool",
        "summary": "Obsolete. Superseded by IPartDoc::ExportToDWG2.}}-->",
    },
    "IPartDoc.ExportToDWG2": {
        "args_count": 9,
        "arg_names": [
            "FilePath",
            "ModelName",
            "Action",
            "ExportToSingleFile",
            "Alignment",
            "IsXDirFlipped",
            "IsYDirFlipped",
            "SheetMetalOptions",
            "Views",
        ],
        "arg_types": [
            "system.string",
            "system.string",
            "system.int",
            "system.bool",
            "system.object",
            "system.bool",
            "system.bool",
            "system.int",
            "system.object",
        ],
        "return_type": "System.bool",
        "summary": "Saves various aspects of a part (sheet metal, faces, loops, and annotation views) to one or more DXF/DWG files, preserving the specified file name.",
    },
    "IPartDoc.GetBodies2": {
        "args_count": 2,
        "arg_names": ["BodyType", "BVisibleOnly"],
        "arg_types": ["system.int", "system.bool"],
        "return_type": "System.object",
        "summary": "Gets the bodies in this part.",
    },
    "IPartDoc.GetMaterialPropertyName2": {
        "args_count": 2,
        "arg_names": ["ConfigName", "Database"],
        "arg_types": ["system.string", "system.string"],
        "return_type": "System.string",
        "summary": "Gets the names of the material database and the material for the specified configuration.",
    },
    "IPartDoc.GetPartBox": {
        "args_count": 1,
        "arg_names": ["NoConversion"],
        "arg_types": ["system.bool"],
        "return_type": "System.object",
        "summary": "Gets the box enclosing the part.",
    },
    "IPartDoc.SetMaterialPropertyName2": {
        "args_count": 3,
        "arg_names": ["ConfigName", "Database", "Name"],
        "arg_types": ["system.string", "system.string", "system.string"],
        "return_type": "void",
        "summary": "Sets the name of the material property for the specified configuration.",
    },
    "ISelectionMgr.GetSelectedObject6": {
        "args_count": 2,
        "arg_names": ["Index", "Mark"],
        "arg_types": ["system.int", "system.int"],
        "return_type": "System.object",
        "summary": "Gets the selected object.",
    },
    "ISelectionMgr.GetSelectedObjectCount2": {
        "args_count": 1,
        "arg_names": ["Mark"],
        "arg_types": ["system.int"],
        "return_type": "System.int",
        "summary": "Gets the number of selected objects.",
    },
    "ISelectionMgr.GetSelectedObjectType3": {
        "args_count": 2,
        "arg_names": ["Index", "Mark"],
        "arg_types": ["system.int", "system.int"],
        "return_type": "System.int",
        "summary": "Gets the type of object selected.",
    },
    "ISelectionMgr.GetSelectedObjectsComponent4": {
        "args_count": 2,
        "arg_names": ["Index", "Mark"],
        "arg_types": ["system.int", "system.int"],
        "return_type": "System.object",
        "summary": "Gets the selected component in an assembly or drawing.",
    },
    "ISelectionMgr.SetSelectedObjectMark": {
        "args_count": 3,
        "arg_names": ["AtIndex", "Mark", "Action"],
        "arg_types": ["system.int", "system.int", "system.int"],
        "return_type": "System.bool",
        "summary": "Sets the mark value for the specified selection.",
    },
    "ISheet.GetName": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.string",
        "summary": "Gets the name of the sheet.",
    },
    "ISheet.GetViews": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the drawing views on this sheet.",
    },
    "ISheet.SetName": {
        "args_count": 1,
        "arg_names": ["NameIn"],
        "arg_types": ["system.string"],
        "return_type": "void",
        "summary": "Sets the sheet name.",
    },
    "ISheet.SetProperties2": {
        "args_count": 8,
        "arg_names": [
            "PaperSz",
            "Templ",
            "Scale1",
            "Scale2",
            "FirstAngle",
            "Width",
            "Height",
            "SameCustomPropAsSheetInDocProp",
        ],
        "arg_types": [
            "system.int",
            "system.int",
            "system.double",
            "system.double",
            "system.bool",
            "system.double",
            "system.double",
            "system.bool",
        ],
        "return_type": "void",
        "summary": "Sets the properties for this sheet.",
    },
    "ISimpleFilletFeatureData2.Initialize": {
        "args_count": 1,
        "arg_names": ["FilletType"],
        "arg_types": ["system.int"],
        "return_type": "System.bool",
        "summary": "Initializes this simple fillet feature to the specified type.",
    },
    "ISketch.GetSketchSegments": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the sketch segments in this sketch, which include line, arc, spline, parabola, and ellipse entities.",
    },
    "ISketch.ModelToSketchTransform": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": None,
        "summary": "Gets the model-to-sketch transform for this sketch. NOTE: This property is a get-only property. Set is not implemented.",
    },
    "ISketchManager.CreateArc": {
        "args_count": 10,
        "arg_names": [
            "XC",
            "YC",
            "Zc",
            "X1",
            "Y1",
            "Z1",
            "X2",
            "Y2",
            "Z2",
            "Direction",
        ],
        "arg_types": [
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.short",
        ],
        "return_type": "SketchSegment",
        "summary": "Creates an arc based on a center point, a start point, an end point, and a direction.",
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
    "ISketchManager.CreateCircleByRadius": {
        "args_count": 4,
        "arg_names": ["XC", "YC", "Zc", "Radius"],
        "arg_types": [
            "system.double",
            "system.double",
            "system.double",
            "system.double",
        ],
        "return_type": "SketchSegment",
        "summary": "Creates a circle based on a center point and a specified radius.",
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
    "ISketchManager.CreateEllipse": {
        "args_count": 9,
        "arg_names": [
            "XC",
            "YC",
            "Zc",
            "XMajor",
            "YMajor",
            "ZMajor",
            "XMinor",
            "YMinor",
            "ZMinor",
        ],
        "arg_types": [
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
        ],
        "return_type": "SketchSegment",
        "summary": "Creates an ellipse using the specified center, major-axis, and minor-axis points.",
    },
    "ISketchManager.CreateLine": {
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
        "summary": "Creates a sketch line in the currently active 2D or 3D sketch.",
    },
    "ISketchManager.CreateParabola": {
        "args_count": 12,
        "arg_names": [
            "XFocus",
            "YFocus",
            "ZFocus",
            "XApex",
            "YApex",
            "ZApex",
            "X1",
            "Y1",
            "Z1",
            "X2",
            "Y2",
            "Z2",
        ],
        "arg_types": [
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
        ],
        "return_type": "SketchSegment",
        "summary": "Creates a parabola in the active sketch.",
    },
    "ISketchManager.CreatePoint": {
        "args_count": 3,
        "arg_names": ["X", "Y", "Z"],
        "arg_types": ["system.double", "system.double", "system.double"],
        "return_type": "SketchPoint",
        "summary": "Creates a sketch point in the active 2D or 3D sketch.",
    },
    "ISketchManager.CreatePolygon": {
        "args_count": 8,
        "arg_names": ["XC", "YC", "Zc", "Xp", "Yp", "Zp", "Sides", "Inscribed"],
        "arg_types": [
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.int",
            "system.bool",
        ],
        "return_type": "System.object",
        "summary": "Creates a polygon in the active sketch.",
    },
    "ISketchManager.CreateSketchSlot": {
        "args_count": 14,
        "arg_names": [
            "SlotCreationType",
            "SlotLengthType",
            "Width",
            "X1",
            "Y1",
            "Z1",
            "X2",
            "Y2",
            "Z2",
            "X3",
            "Y3",
            "Z3",
            "CenterArcDirection",
            "AddDimension",
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
            "system.double",
            "system.double",
            "system.double",
            "system.double",
            "system.int",
            "system.bool",
        ],
        "return_type": "SketchSlot",
        "summary": "Creates a sketch slot.",
    },
    "ISketchManager.CreateSpline2": {
        "args_count": 2,
        "arg_names": ["PointData", "SimulateNaturalEnds"],
        "arg_types": ["system.object", "system.bool"],
        "return_type": "SketchSegment",
        "summary": "Obsolete. Superseded by ISketchManager::CreateSpline3.",
    },
    "ISketchManager.Insert3DSketch": {
        "args_count": 1,
        "arg_names": ["UpdateEditRebuild"],
        "arg_types": ["system.bool"],
        "return_type": "void",
        "summary": "Inserts a new 3D sketch in a model or closes the active sketch.",
    },
    "ISketchManager.InsertSketch": {
        "args_count": 1,
        "arg_names": ["UpdateEditRebuild"],
        "arg_types": ["system.bool"],
        "return_type": "void",
        "summary": "Inserts a new sketch in the current part or assembly document.",
    },
    "ISketchRelationManager.DeleteRelation": {
        "args_count": 1,
        "arg_names": ["ThisRelation"],
        "arg_types": ["sketchrelation"],
        "return_type": "System.bool",
        "summary": "Deletes the specified logical sketch relation in sketch.",
    },
    "ISketchRelationManager.GetRelations": {
        "args_count": 1,
        "arg_names": ["Filter"],
        "arg_types": ["system.int"],
        "return_type": "System.object",
        "summary": "Gets all of the sketch relations in the sketch based on the specified filter.",
    },
    "ISketchSegment.ConstructionGeometry": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": None,
        "summary": "Gets or sets whether this sketch segment is construction geometry, for example, a centerline for a feature revolve operation.",
    },
    "ISketchText.GetTextFormat": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the text format for this sketch text.",
    },
    "ISketchText.SetTextFormat": {
        "args_count": 2,
        "arg_names": ["UseDoc", "TextFormat"],
        "arg_types": ["system.bool", "system.object"],
        "return_type": "System.bool",
        "summary": "Sets the text format for this sketch text.",
    },
    "ISldWorks.CloseDoc": {
        "args_count": 1,
        "arg_names": ["Name"],
        "arg_types": ["system.string"],
        "return_type": "void",
        "summary": "Closes the specified document.",
    },
    "ISldWorks.GetExportFileData": {
        "args_count": 1,
        "arg_names": ["FileType"],
        "arg_types": ["system.int"],
        "return_type": "System.object",
        "summary": "Gets the data interface for the specified file type to which to export one or more drawing sheets.",
    },
    "ISldWorks.GetHoleStandardsData": {
        "args_count": 1,
        "arg_names": ["HoleTypeID"],
        "arg_types": ["system.int"],
        "return_type": "System.object",
        "summary": "Gets the hole standards for the specified hole type.",
    },
    "ISldWorks.GetImportFileData": {
        "args_count": 1,
        "arg_names": ["FileName"],
        "arg_types": ["system.string"],
        "return_type": "System.object",
        "summary": "Gets the IGES or DXF/DWG import data for the specified file.",
    },
    "ISldWorks.GetMathUtility": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets IMathUtility.",
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
    "ISldWorks.LoadFile4": {
        "args_count": 4,
        "arg_names": ["FileName", "ArgString", "ImportData", "Errors"],
        "arg_types": ["system.string", "system.string", "system.object", "system.int"],
        "return_type": "ModelDoc2",
        "summary": "Loads a third-party native CAD file into a new SOLIDWORKS document using 3D Interconnect.",
    },
    "ISldWorks.NewDocument": {
        "args_count": 4,
        "arg_names": ["TemplateName", "PaperSize", "Width", "Height"],
        "arg_types": ["system.string", "system.int", "system.double", "system.double"],
        "return_type": "System.object",
        "summary": "Creates a new document based on the specified template.",
    },
    "ISldWorks.OpenDoc6": {
        "args_count": 6,
        "arg_names": [
            "FileName",
            "Type",
            "Options",
            "Configuration",
            "Errors",
            "Warnings",
        ],
        "arg_types": [
            "system.string",
            "system.int",
            "system.int",
            "system.string",
            "system.int",
            "system.int",
        ],
        "return_type": "ModelDoc2",
        "summary": "Opens an existing document and returns a pointer to the document object.",
    },
    "ISldWorks.SetUserPreferenceToggle": {
        "args_count": 2,
        "arg_names": ["UserPreferenceValue", "OnFlag"],
        "arg_types": ["system.int", "system.bool"],
        "return_type": "void",
        "summary": "Sets system default user preference values.",
    },
    "ISurface.Evaluate": {
        "args_count": 4,
        "arg_names": ["UParam", "VParam", "NumUDeriv", "NumVDeriv"],
        "arg_types": ["system.double", "system.double", "system.int", "system.int"],
        "return_type": "System.object",
        "summary": "Evaluates the surface, given the u and v parameters of the surface.",
    },
    "ISurface.IsCylinder": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.bool",
        "summary": "Gets whether the surface is a cylinder.",
    },
    "ISurface.IsPlane": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.bool",
        "summary": "Gets whether the surface is a planar surface.",
    },
    "ISurface.Parameterization": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Obsolete. Superseded by ISurface::Parameterization2.",
    },
    "IView.GetAnnotationCount": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.int",
        "summary": "Gets the number of annotations in this view.",
    },
    "IView.GetAnnotations": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the annotations in this view.",
    },
    "IView.GetDisplayDimensions": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets all of the display dimension on this drawing view.",
    },
    "IView.GetName2": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.string",
        "summary": "Gets the name of this drawing view displayed in the FeatureManager design tree.",
    },
    "IView.GetOutline": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.object",
        "summary": "Gets the bounding box for a view (sheet or drawing) in meters on the drawing page.",
    },
    "IView.GetTableAnnotationCount": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "System.int",
        "summary": "Gets the number of table annotations in this drawing view.",
    },
    "IView.IGetBomTable": {
        "args_count": 0,
        "arg_names": [],
        "arg_types": [],
        "return_type": "BomTable",
        "summary": "Gets the BOM table found in this drawing view.",
    },
    "IView.InsertBomTable4": {
        "args_count": 10,
        "arg_names": [
            "UseAnchorPoint",
            "X",
            "Y",
            "AnchorType",
            "BomType",
            "Configuration",
            "TableTemplate",
            "Hidden",
            "IndentedNumberingType",
            "DetailedCutList",
        ],
        "arg_types": [
            "system.bool",
            "system.double",
            "system.double",
            "system.int",
            "system.int",
            "system.string",
            "system.string",
            "system.bool",
            "system.int",
            "system.bool",
        ],
        "return_type": "BomTableAnnotation",
        "summary": "Obsolete. Superseded by IView::InsertBomTable5.",
    },
    "IWizardHoleFeatureData2.InitializeHole": {
        "args_count": 5,
        "arg_names": ["GenericHoleType", "StdIndex", "FastnerType", "SSize", "EndType"],
        "arg_types": [
            "system.int",
            "system.int",
            "system.int",
            "system.string",
            "system.int",
        ],
        "return_type": "void",
        "summary": "Initializes a newly created Hole Wizard feature data object.",
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
