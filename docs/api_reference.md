# SOLIDWORKS API Reference (verified)

Auto-generated from decompiled `sldworksapi.chm` + `swconst.chm`. 
Regenerate with `tools/chm_extract.py batch tools/_api_extract_input.json api_reference.json` 
then `tools/gen_api_markdown.py api_reference.json api_reference.md`.

**Authoritative for arg counts and types on this SW build.** When an SW API
call fails `PARAMNOTOPTIONAL` or `Invalid number of parameters`, the first check
is whether the arg count here matches what's being passed. ([builder.py FeatureCut4 was 27 args, not 24](src/ai_sw_bridge/spec/builder.py))

## Methods

### `IEquationMgr.Add2`

Adds an equation at the specified index.

**Args (3):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Index` | `system.int` | 0-based index of the new equation (-1 places it at the end of the list) |
| 2 | `Equation` | `system.string` | String containing the equation (see Remarks) |
| 3 | `Solve` | `system.bool` | True to solve the equation immediately; false otherwise (see Remarks) |

**Returns:** `System.int`

**Availability:** SOLIDWORKS 2010 FCS, Revision Number 18.0

### `IFeature.GetNextFeature`

Gets the next feature in the part.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.object`

### `IFeature.GetTypeName`

Gets the type of feature. NOTE: To get the underlying type of feature of an Instant3D feature (i.e., "ICE"), call this method; otherwise, call IFeature::GetTypeName2.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.string`

### `IFeatureManager.FeatureCut4`

Creates a cut extrude feature.

**Args (27):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Sd` | `system.bool` | True for a single-ended cut, false for a doubled-ended cut |
| 2 | `Flip` | `system.bool` | True to remove material outside of the profile of the flip side to cut, false to not |
| 3 | `Dir` | `system.bool` | True for Direction 1 to be opposite of the default direction (see Remarks) |
| 4 | `T1` | `system.int` | Termination type for the first end as defined in swEndConditions_e |
| 5 | `T2` | `system.int` | Termination type for the second end as defined in swEndConditions_e |
| 6 | `D1` | `system.double` | Depth of extrusion for the first end in meters |
| 7 | `D2` | `system.double` | Depth of extrusion for the second end in meters |
| 8 | `Dchk1` | `system.bool` | True allows a draft angle in the first direction, false does not allow drafting in the first direction |
| 9 | `Dchk2` | `system.bool` | True allows a draft angle in the second direction, false does not allow drafting in the second direction |
| 10 | `Ddir1` | `system.bool` | True for the first draft angle to be inward, false to be outward; only valid when Dchk1 is true |
| 11 | `Ddir2` | `system.bool` | True for the second draft angle to be inward, false to be outward; only valid when Dchk2 is true |
| 12 | `Dang1` | `system.double` | Draft angle for the first end; only valid when Dchk1 is true |
| 13 | `Dang2` | `system.double` | Draft angle for the second end; only valid when Dchk2 is true |
| 14 | `OffsetReverse1` | `system.bool` | If you chose to offset the first end condition from another face or plane, then true specifies offset in direction away from the sketch, false specifies offset from the face or plane in a direction... |
| 15 | `OffsetReverse2` | `system.bool` | If you chose to offset the second end condition from another face or plane, then true specifies offset in direction away from the sketch, false specifies offset from the face or plane in a directio... |
| 16 | `TranslateSurface1` | `system.bool` | When you choose swEndConditions_e.swEndCondOffsetFromSurface as the termination type for the first end, then true specifies that the end of the extrusion is a translation of the reference surface, ... |
| 17 | `TranslateSurface2` | `system.bool` | When you choose swEndConditions_e.swEndCondOffsetFromSurface as the termination type for the second end, then true specifies that the end of the extrusion is a translation of the reference surface,... |
| 18 | `NormalCut` | `system.bool` | True to create the cut normal to the sheet metal thickness, false to not (only valid for sheet metal parts; use false for non-sheet metal parts) |
| 19 | `UseFeatScope` | `system.bool` | True if the feature only affects selected bodies or components, false if the feature affects all bodies or components |
| 20 | `UseAutoSelect` | `system.bool` | True to automatically select all bodies or components and have the feature affect those bodies or components, false to only select the bodies or components the feature affects (see Remarks) |
| 21 | `AssemblyFeatureScope` | `system.bool` | True if the assembly feature only affects selected components in the assembly, false if the assembly feature affects all components in the assembly |
| 22 | `AutoSelectComponents` | `system.bool` | True to automatically select all affected components, false to use only the selected components |
| 23 | `PropagateFeatureToParts` | `system.bool` | True to propagate the assembly feature to the components in the model that it affects, false to not |
| 24 | `T0` | `system.int` | Start conditions as defined in swStartConditions_e |
| 25 | `StartOffset` | `system.double` | If T0 is swStartConditions_e.swStartOffset, then specify an offset value |
| 26 | `FlipStartOffset` | `system.bool` | If T0 is swStartConditions_e.swStartOffset, then true to flip the direction of cut, false to not |
| 27 | `OptimizeGeometry` | `system.bool` | True to optimize the normal cut in a sheet metal part, false to not; only valid for sheet metal parts and when NormalCut is true |

**Returns:** `Feature`

**Availability:** SOLIDWORKS 2017 FCS, Revision Number 25.0

### `IFeatureManager.FeatureExtrusion2`

Obsolete. Superseded by IFeatureManager::FeatureExtrusion3.

**Args (23):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Sd` | `system.bool` | True for single ended, false for double ended |
| 2 | `Flip` | `system.bool` | True to flip side to cut |
| 3 | `Dir` | `system.bool` | True to flip the direction to extrude |
| 4 | `T1` | `system.int` | Termination type for first end as defined in swEndConditions_e |
| 5 | `T2` | `system.int` | Termination type for second end as defined in swEndConditions_e |
| 6 | `D1` | `system.double` | Depth of extrusion for first end in meters |
| 7 | `D2` | `system.double` | Depth of extrusion for second end in meters |
| 8 | `Dchk1` | `system.bool` | True allows draft angle in first direction, false does not allow drafting |
| 9 | `Dchk2` | `system.bool` | True allows draft angle in second direction, false does not allow drafting |
| 10 | `Ddir1` | `system.bool` | True for first draft angle to be inward, false to be outward |
| 11 | `Ddir2` | `system.bool` | True for second draft angle to be inward, false to be outward |
| 12 | `Dang1` | `system.double` | Draft angle for first end |
| 13 | `Dang2` | `system.double` | Draft angle for second end |
| 14 | `OffsetReverse1` | `system.bool` | If you chose to offset the first end condition from another face or plane, then True specifies offset in direction away from the sketch, false specifies offset from the face or plane in direction t... |
| 15 | `OffsetReverse2` | `system.bool` | If you chose to offset the second end condition from another face or plane, then True specifies offset in direction away from the sketch, false specifies offset from the face or plane in direction ... |
| 16 | `TranslateSurface1` | `system.bool` | When you choose swEndcondOffsetFromSurface as the termination type for the first end, then True specifies that the end of the extrusion is a translation of the reference surface, false specifies to... |
| 17 | `TranslateSurface2` | `system.bool` | When you choose swEndcondOffsetFromSurface as the termination type for the second end, then True specifies that the end of the extrusion is a translation of the reference surface, false specifies t... |
| 18 | `Merge` | `system.bool` | True to merge the results in a multibody part, false to not |
| 19 | `UseFeatScope` | `system.bool` | True if the feature only affects selected bodies, false if the feature affects all bodies |
| 20 | `UseAutoSelect` | `system.bool` | True to automatically select all bodies and have the feature affect those bodies, false to select the bodies the feature affects (see Remarks) |
| 21 | `T0` | `system.int` | Start condition as defined in swStartConditions_e |
| 22 | `StartOffset` | `system.double` | If t0 set to swStartOffset, then specify offset value |
| 23 | `FlipStartOffset` | `system.bool` | If t0 set to swStartOffset, then True to flip the direction or false to not |

**Returns:** `Feature`

**Availability:** SOLIDWORKS 2005 FCS, Revision Number 13.0

### `IFeatureManager.FeatureExtrusion3`

Creates an extruded feature.

**Args (23):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Sd` | `system.bool` | True for single ended, false for double ended |
| 2 | `Flip` | `system.bool` | True to flip the side to cut |
| 3 | `Dir` | `system.bool` | True to flip the direction of extrusion |
| 4 | `T1` | `system.int` | Termination type for first end of the extrusion as defined in swEndConditions_e |
| 5 | `T2` | `system.int` | Termination type for second end of the extrusion as defined in swEndConditions_e |
| 6 | `D1` | `system.double` | Depth of extrusion for first end in meters; offset, if T1 is set to swEndConditions_e.swEndCondOffsetFromSurface |
| 7 | `D2` | `system.double` | Depth of extrusion for second end in meters; offset, if T2 is set to swEndConditions_e.swEndCondOffsetFromSurface |
| 8 | `Dchk1` | `system.bool` | True to allow drafting in the first direction, false to not |
| 9 | `Dchk2` | `system.bool` | True to allow drafting in the second direction, false to not |
| 10 | `Ddir1` | `system.bool` | True for first draft angle to be inward, false to be outward; valid only if Dchk1 is true |
| 11 | `Ddir2` | `system.bool` | True for second draft angle to be inward, false to be outward; valid only if Dchk2 is true |
| 12 | `Dang1` | `system.double` | Draft angle for first end; valid only if Dchk1 is true |
| 13 | `Dang2` | `system.double` | Draft angle for second end; valid only if Dchk2 is true |
| 14 | `OffsetReverse1` | `system.bool` | True to offset the first end from another face or plane in a direction away from the sketch, false to offset in a direction toward the sketch; valid only if T1 is set to swEndConditions_e.swEndCond... |
| 15 | `OffsetReverse2` | `system.bool` | True to offset the second end from another face or plane in a direction away from the sketch, false to offset in a direction toward the sketch; valid only if T2 is set to swEndConditions_e.swEndCon... |
| 16 | `TranslateSurface1` | `system.bool` | True if the first end of the extrusion is a translation of the reference surface, false if it has a true offset; valid only if T1 is set to swEndConditions_e.swEndCondOffsetFromSurface |
| 17 | `TranslateSurface2` | `system.bool` | True if the second end of the extrusion is a translation of the reference surface, false if it has a true offset; valid only if T2 is set to swEndConditions_e.swEndCondOffsetFromSurface |
| 18 | `Merge` | `system.bool` | True to merge the results in a multibody part, false to not |
| 19 | `UseFeatScope` | `system.bool` | True if the feature only affects selected bodies, false if the feature affects all bodies (see Remarks) |
| 20 | `UseAutoSelect` | `system.bool` | True to automatically select all bodies and have the feature affect those bodies, false to select the bodies that the feature affects (see Remarks) |
| 21 | `T0` | `system.int` | Start condition as defined in swStartConditions_e |
| 22 | `StartOffset` | `system.double` | Distance from the sketch plane to start the extrude; valid only if T0 is set to swStartConditions_e.swStartOffset |
| 23 | `FlipStartOffset` | `system.bool` | True to flip the direction of the start offset, false to not; valid only if T0 is set to swStartConditions_e.swStartOffset |

**Returns:** `Feature`

**Availability:** SOLIDWORKS 2014 FCS, Revision Number 22.0

### `IModelDoc2.AddDimension2`

Creates a display dimension at the specified location for selected entities.

**Args (3):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `X` | `system.double` | Dimension text location in meters |
| 2 | `Y` | `system.double` | Dimension text location in meters |
| 3 | `Z` | `system.double` | Dimension text location in meters |

**Returns:** `System.object`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IModelDoc2.ClearSelection2`

Clears the selection list.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `All` | `system.bool` | True clears the entire existing selection list, false clears only the items in the active selection list (see Remarks) |

**Returns:** `void`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IModelDoc2.EditRebuild3`

Rebuilds only those features that need to be rebuilt in the active configuration in the model.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.bool`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IModelDoc2.EditUndo2`

Undoes the specified number of actions in the active SOLIDWORKS session.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Steps` | `system.int` | Number of actions to undo |

**Returns:** `void`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IModelDoc2.FeatureByPositionReverse`

Gets the nth from last feature in the document.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Num` | `system.int` | Number of feature from the last feature in the FeatureManager design tree; 0 is the last feature in FeatureManager design tree |

**Returns:** `System.object`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IModelDoc2.GetFeatureCount`

Gets the number of features in this document.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.int`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IModelDoc2.Parameter`

Gets the specified parameter.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `StringIn` | `system.string` | Name of parameter (for example, "D1@Base-Revolve") |

**Returns:** `System.object`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IModelDoc2.SaveBMP`

Saves the current view as a bitmap (BMP) file.

**Args (3):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `FileNameIn` | `system.string` | Path and file name of the new BMP file |
| 2 | `WidthIn` | `system.int` | Width of the BMP |
| 3 | `HeightIn` | `system.int` | Height of the BMP |

**Returns:** `System.bool`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IModelDoc2.SelectByID`

Obsolete. Superseded by IModelDocExtension::SelectByID2.

**Args (5):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `SelID` | `system.string` |  |
| 2 | `SelParams` | `system.string` |  |
| 3 | `X` | `system.double` |  |
| 4 | `Y` | `system.double` |  |
| 5 | `Z` | `system.double` |  |

**Returns:** `System.bool`

### `IModelDocExtension.SelectByID2`

Selects the specified entity.

**Args (9):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Name` | `system.string` | Name of object to select or an empty string |
| 2 | `Type` | `system.string` | Type of object (uppercase) as defined in swSelectType_e or an empty string |
| 3 | `X` | `system.double` | X selection location or 0 |
| 4 | `Y` | `system.double` | Y selection location or 0 |
| 5 | `Z` | `system.double` | Z selection location or 0 |
| 6 | `Append` | `system.bool` | If... An, if entity is... Then... True Not already selected Entity is appended to the current selection list Already selected Entity is removed from the current selection list False Not already sel... |
| 7 | `Mark` | `system.int` | Value that you want to use as a mark; this value is used by other functions that require ordered selection (see Remarks) |
| 8 | `Callout` | `callout` | Pointer to the associated callout |
| 9 | `SelectOption` | `system.int` | Selection option as defined in swSelectOption_e (see Remarks) |

**Returns:** `System.bool`

**Availability:** SOLIDWORKS 2005 FCS, Revision Number 13.0

### `ISketchManager.CreateCenterRectangle`

Creates a center rectangle.

**Args (6):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `X1` | `system.double` | X coordinate for point 1 |
| 2 | `Y1` | `system.double` | Y coordinate for point 1 |
| 3 | `Z1` | `system.double` | Z coordinate for point 1 |
| 4 | `X2` | `system.double` | X coordinate for point 2 |
| 5 | `Y2` | `system.double` | Y coordinate for point 2 |
| 6 | `Z2` | `system.double` | Z coordinate for point 2 |

**Returns:** `System.object`

### `ISketchManager.CreateCircle`

Creates a circle based on a center point and a point on the circle.

**Args (6):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `XC` | `system.double` | X coordinate of the circle center point, in meters |
| 2 | `YC` | `system.double` | Y coordinate of the circle center point, in meters |
| 3 | `Zc` | `system.double` | Z coordinate of the circle center point, in meters |
| 4 | `Xp` | `system.double` | X coordinate of the point on the circle, in meters |
| 5 | `Yp` | `system.double` | Y coordinate of the point on the circle, in meters |
| 6 | `Zp` | `system.double` | Z coordinate of the point on the circle, in meters |

**Returns:** `SketchSegment`

**Availability:** SOLIDWORKS 2008 FCS, Revision Number 16.0

### `ISketchManager.CreateCornerRectangle`

Creates a corner rectangle.

**Args (6):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `X1` | `system.double` | Upper-left X coordinate for point 1 |
| 2 | `Y1` | `system.double` | Upper-left Y coordinate for point 1 |
| 3 | `Z1` | `system.double` | Upper-left Z coordinate for point 1 |
| 4 | `X2` | `system.double` | Lower-right X coordinate for point 2 |
| 5 | `Y2` | `system.double` | Lower-right Y coordinate for point 2 |
| 6 | `Z2` | `system.double` | Lower-right Z coordinate for point 2 |

**Returns:** `System.object`

**Availability:** SOLIDWORKS 2008 FCS, Revision Number 16.0

### `ISketchManager.InsertSketch`

Inserts a new sketch in the current part or assembly document.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `UpdateEditRebuild` | `system.bool` | True to rebuild the part with any changes made to the sketch and exit sketch mode, false to not |

**Returns:** `void`

**Availability:** SOLIDWORKS 2007 FCS, Revision Number 15.0

### `ISldWorks.GetUserPreferenceStringValue`

Gets system default user preference values.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `UserPreference` | `system.int` | User preference as defined in swUserPreferenceStringValue_e |

**Returns:** `System.string`

**Availability:** SOLIDWORKS 2000 FCS, Revision Number 8.0

### `ISldWorks.GetUserPreferenceToggle`

Gets document default user preference values.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `UserPreferenceToggle` | `system.int` | User preference as defined in swUserPreferenceToggle_e |

**Returns:** `System.bool`

### `ISldWorks.NewDocument`

Creates a new document based on the specified template.

**Args (4):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `TemplateName` | `system.string` | Fully qualified path and name of the template to use for creating the new document |
| 2 | `PaperSize` | `system.int` | Size of paper as defined in swDwgPaperSizes_e |
| 3 | `Width` | `system.double` | Width of paper; used only when PaperSize is swDwgPapersUserDefined |
| 4 | `Height` | `system.double` | Height of paper; used only when PaperSize is swDwgPapersUserDefined |

**Returns:** `System.object`

**Availability:** SOLIDWORKS 2000 FCS, Revision Number 8.0

### `ISldWorks.SetUserPreferenceToggle`

Sets system default user preference values.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `UserPreferenceValue` | `system.int` | User preference as defined in swUserPreferenceToggle_e |
| 2 | `OnFlag` | `system.bool` | True to toggle UserPreferenceValue on, false to toggle UserPreferenceValue off |

**Returns:** `void`

## Enums

### `swDimensionType_e`

Types of dimensions.

| Name | Value | Doc |
|------|-------|-----|
| `swDimensionTypeUnknown` | `0` | Dimension type could not be determined |
| `swOrdinateDimension` | `1` | Base ordinate and its subordinates are of this type |
| `swLinearDimension` | `2` | Linear dimension type |
| `swAngularDimension` | `3` | Angular dimension type |
| `swArcLengthDimension` | `4` | Arc length dimension type |
| `swRadialDimension` | `5` | Radial dimension |
| `swDiameterDimension` | `6` | Diameter dimension |
| `swHorOrdinateDimension` | `7` | Horizontal ordinate dimension |
| `swVertOrdinateDimension` | `8` | Vertical ordinate dimension |
| `swZAxisDimension` | `9` |  |
| `swChamferDimension` | `10` |  |
| `swHorLinearDimension` | `11` | Horizontal linear dimension |
| `swVertLinearDimension` | `12` | Vertical linear dimension |
| `swScalarDimension` | `13` |  |
| `swRadialLinearDimension` | `14` | Doubled distance radial dimension |
| `swDiametricLinearDimension` | `15` | Doubled distance linear dimension |
| `swAngularOrdinateDimension` | `16` | Angular ordinate dimension |

### `swDocumentTypes_e`

Document types.

| Name | Value | Doc |
|------|-------|-----|
| `swDocNONE` | `0` |  |
| `swDocPART` | `1` |  |
| `swDocASSEMBLY` | `2` |  |
| `swDocDRAWING` | `3` |  |
| `swDocSDM` | `4` |  |
| `swDocLAYOUT` | `5` |  |
| `swDocIMPORTED_PART` | `6` |  |
| `swDocIMPORTED_ASSEMBLY` | `7` |  |

### `swEndConditions_e`

End conditions for creation of a variety of features.

| Name | Value | Doc |
|------|-------|-----|
| `swEndCondBlind` | `0` |  |
| `swEndCondThroughAll` | `1` |  |
| `swEndCondThroughNext` | `2` |  |
| `swEndCondUpToVertex` | `3` | Do not use; superseded by swEndCondUpToSelection |
| `swEndCondUpToSurface` | `4` | Do not use; superseded by swEndCondUpToSelection |
| `swEndCondOffsetFromSurface` | `5` |  |
| `swEndCondMidPlane` | `6` |  |
| `swEndCondUpToBody` | `7` |  |
| `swEndCondThroughAllBoth` | `9` |  |
| `swEndCondUpToSelection` | `10` |  |
| `swEndCondUpToNext` | `11` |  |

### `swSelectType_e`

Values for types of returned IDs.

| Name | Value | Doc |
|------|-------|-----|

### `swStartConditions_e`

Start conditions.

| Name | Value | Doc |
|------|-------|-----|
| `swStartSketchPlane` | `0` |  |
| `swStartSurface` | `1` |  |
| `swStartVertex` | `2` |  |
| `swStartOffset` | `3` |  |

## Not found in CHM

- `method:ISldWorks.SendKeys`
- `method:IFeatureManager.FeatureCut5`
