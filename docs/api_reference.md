# SOLIDWORKS API Reference (verified)

Auto-generated from decompiled `sldworksapi.chm` + `swconst.chm`. 
Regenerate with `tools/chm_extract.py batch tools/_api_extract_input.json api_reference.json` 
then `tools/gen_api_markdown.py api_reference.json api_reference.md`.

**Authoritative for arg counts and types on this SW build.** When an SW API
call fails `PARAMNOTOPTIONAL` or `Invalid number of parameters`, the first check
is whether the arg count here matches what's being passed. ([builder.py FeatureCut4 was 27 args, not 24](src/ai_sw_bridge/spec/builder.py))

## Methods

### `IAssemblyDoc.AddMate5`

Obsolete. Superseded by IAssemblyDoc::CreateMate.

**Args (15):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `MateTypeFromEnum` | `system.int` | Type of mate as defined in swMateType_e (see Remarks) |
| 2 | `AlignFromEnum` | `system.int` | Type of alignment as defined in swMateAlign_e |
| 3 | `Flip` | `system.bool` | True to flip the mate entities, false to not; valid only if MateTypeFromEnum is swMatetype_e.swMateDISTANCE |
| 4 | `Distance` | `system.double` | Distance value; valid only if MateTypeFromEnum is swMateType_e.swMateDISTANCE |
| 5 | `DistanceAbsUpperLimit` | `system.double` | Absolute maximum distance value; valid only if MateTypeFromEnum is swMateType_e.swMateDISTANCE (see Remarks) |
| 6 | `DistanceAbsLowerLimit` | `system.double` | Absolute minimum distance value; valid only if MateTypeFromEnum is swMateType_e.swMateDISTANCE (see Remarks) |
| 7 | `GearRatioNumerator` | `system.double` | Gear ratio numerator value; valid only if MateTypeFromEnum is swMateType_e.swMateGEAR |
| 8 | `GearRatioDenominator` | `system.double` | Gear ratio denominator value; valid only if MateTypeFromEnum is swMateType_e.swMateGEAR |
| 9 | `Angle` | `system.double` | Angle value; valid only if MateTypeFromEnum is swMateType_e.swMateANGLE |
| 10 | `AngleAbsUpperLimit` | `system.double` | Absolute maximum angle value; valid only if MateTypeFromEnum is swMateType_e.swMateANGLE |
| 11 | `AngleAbsLowerLimit` | `system.double` | Absolute minimum angle value; valid only if MateTypeFromEnum is swMateType_e.swMateANGLE |
| 12 | `ForPositioningOnly` | `system.bool` | True to only position the components according to the mating relationship and not return a mate, false to return a mate |
| 13 | `LockRotation` | `system.bool` | True to lock component rotation, false to not |
| 14 | `WidthMateOption` | `system.int` | Width mate options as defined in swMateWidthOptions_e; valid only if MateTypeFromEnum is swMateType_e.swMateWIDTH |
| 15 | `ErrorStatus` | `system.int` | Success or error as defined by swAddMateError_e |

**Returns:** `Mate2`

**Availability:** SOLIDWORKS 2015 FCS, Revision Number 23.0

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

### `IFeatureManager.CreateDefinition`

Creates a feature data object of the specified type.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Type` | `system.int` | Feature name ID as defined in swFeatureNameID_e: swFMBaseFlange (sheet metal base flange) swFMBeltAndChain (belt/chain) swFmBoundingBox (bounding box) swFmCirPattern (circular pattern) swFmCornerRe... |

**Returns:** `System.object`

**Availability:** SOLIDWORKS 2006 FCS, Revision Number 14.0

### `IFeatureManager.CreateFeature`

Creates the specified feature.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `FeatureData` | `system.object` | thread, sweep, library, tab/slot, bounding box, ground plane, mirror components, projection curve, sheet metal normal cut, sheet metal swept flange, sheet metal gusset, sheet metal edge flange, sim... |

**Returns:** `Feature`

**Availability:** SOLIDWORKS 2006 FCS, Revision Number 14.0

### `IFeatureManager.FeatureCircularPattern5`

Obsolete. See IFeatureManager::CreateFeature and the Remarks in ICircularPatternFeatureData and ILocalCircularPatternFeatureData.

**Args (14):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Number` | `system.int` | Number of instances of the circular pattern to insert in Direction 1, including the original instance |
| 2 | `Spacing` | `system.double` | Spacing between each instance in Direction 1 of the circular pattern or, if EqualSpacing is true, then the total angle in radians |
| 3 | `FlipDirection` | `system.bool` | True to flip the direction of the circular pattern in Direction 1, false to not |
| 4 | `DName` | `system.string` | Name of the angular dimension defining Direction 1 of the pattern |
| 5 | `GeometryPattern` | `system.bool` | True to use geometry pattern, false to not |
| 6 | `EqualSpacing` | `system.bool` | True to use equal spacing in Direction 1, false to not |
| 7 | `VaryInstance` | `system.bool` | True to vary the dimensions or spacing of individual pattern instances, false to not; valid only if GeometryPattern = false (see Remarks) |
| 8 | `SyncSubAssemblies` | `system.bool` | True to move components in the patterned instances when components are moved in the seed flexible subassembly, false to not |
| 9 | `BDir2` | `system.bool` | True to create a bidirectional circular pattern feature, false to not |
| 10 | `BSymmetric` | `system.bool` | True to create a symmetric circular pattern feature in Direction 2, false to create an asymmetrical circular pattern feature in Direction 2; valid only if BDir2 is true |
| 11 | `Number2` | `system.int` | Number of instances to insert in Direction 2; valid only if BDir2 is true |
| 12 | `Spacing2` | `system.double` | Distance between pattern instances in Direction 2; valid only if BDir2 is true |
| 13 | `DName2` | `system.string` | Name of the angular dimension defining Direction 2 of the pattern; valid only if BDir2 is true |
| 14 | `EqualSpacing2` | `system.bool` | True to use equal spacing in Direction 2, false to not; valid only if BDir2 is true and BSymmetric is false |

**Returns:** `Feature`

**Availability:** SOLIDWORKS 2017 FCS, Revision Number 25.0

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

### `IFeatureManager.FeatureLinearPattern5`

Obsolete. See IFeatureManager::CreateFeature and the Remarks in ILinearPatternFeatureData and ILocalLinearPatternFeatureData.

**Args (22):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Num1` | `system.int` | Number of instances of the linear pattern in Direction 1, including the original |
| 2 | `Spacing1` | `system.double` | Spacing in meters between each instance of the linear pattern in Direction 1 |
| 3 | `Num2` | `system.int` | Number of instances of the linear pattern in Direction 2, including the original |
| 4 | `Spacing2` | `system.double` | Spacing in meters between each instance of the linear pattern in Direction 2 |
| 5 | `FlipDir1` | `system.bool` | True to reverse the direction of the linear pattern in Direction 1, false to not |
| 6 | `FlipDir2` | `system.bool` | True to reverse the direction of the linear pattern in Direction 2, false to not |
| 7 | `DName1` | `system.string` | Name of the dimension defining Direction 1 |
| 8 | `DName2` | `system.string` | Name of the dimension defining Direction 2 |
| 9 | `GeometryPattern` | `system.bool` | True to use geometry pattern, false to not |
| 10 | `VaryInstance` | `system.bool` | True to vary the dimensions and spacing of individual pattern instances, false to not; valid only if GeometryPattern = false (see Remarks) |
| 11 | `HasOffset1` | `system.bool` | True if using Offset1 to specify an offset of the pattern seed from a selected reference in Direction 1, false if not |
| 12 | `HasOffset2` | `system.bool` | True if using Offset2 to specify an offset of the pattern seed from a selected reference in Direction 2, false if not |
| 13 | `CtrlByNum1` | `system.bool` | True to control pattern spacing using Num1, false to control it using Spacing1; valid only if HasOffset1 is true |
| 14 | `CtrlByNum2` | `system.bool` | True to control pattern spacing using Num2, false to control it using Spacing2; valid only if HasOffset2 is true |
| 15 | `FromCentroid1` | `system.bool` | True if Offset1 is measured from the centroid of the seed instance, false if it is measured from a selected reference on the seed instance; valid only if HasOffset1 is true (see Remarks) |
| 16 | `FromCentroid2` | `system.bool` | True if Offset2 is measured from the centroid of the seed instance, false if it is measured from a selected reference on the seed instance; valid only if HasOffset2 is true (see Remarks) |
| 17 | `RevOffset1` | `system.bool` | True to reverse the direction of Offset1, false to not; valid only if HasOffset1 is true |
| 18 | `RevOffset2` | `system.bool` | True to reverse the direction of Offset2, false to not; valid only if HasOffset2 is true |
| 19 | `Offset1` | `system.double` | Offset in meters from a selected reference in Direction 1; valid only if HasOffset1 is true (see Remarks) |
| 20 | `Offset2` | `system.double` | Offset in meters from a selected reference in Direction 2; valid only if HasOffset2 is true (see Remarks) |
| 21 | `D2PatternSeedOnly` | `system.bool` | True to create a linear pattern in Direction 2 using the seed features only, without replicating the pattern instances of Direction 1; false to not |
| 22 | `SyncSubAssemblies` | `system.bool` | True to move components in the patterned instances when components are moved in the seed flexible subassembly, false to not |

**Returns:** `Feature`

**Availability:** SOLIDWORKS 2017 FCS, Revision Number 25.0

### `IFeatureManager.FeatureRevolve2`

Creates a base-, boss-, or cut-revolve feature.

**Args (20):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `SingleDir` | `system.bool` | True if the revolve is in one direction, false if in two directions (see Remarks) |
| 2 | `IsSolid` | `system.bool` | True if this is a solid revolve feature, false if not |
| 3 | `IsThin` | `system.bool` | True if this is a thin revolve feature, false if not |
| 4 | `IsCut` | `system.bool` | True if this is a cut revolve feature, false if not |
| 5 | `ReverseDir` | `system.bool` | True reverses the angle of the revolution, false does not; only applies if Dir1Type is not swEndConditions_e.swEndCondMidPlane |
| 6 | `BothDirectionUpToSameEntity` | `system.bool` | True if the revolve is up to the same entity in both directions, false if not; only applies if SingleDir is false and Dir1Type and Dir2Type are swEndConditions_e.swEndCondUpToVertex, swEndCondition... |
| 7 | `Dir1Type` | `system.int` | Revolve end condition as defined in swEndConditions_e |
| 8 | `Dir2Type` | `system.int` | Revolve end condition in direction 2; as defined in swEndConditions_e and only applies if Dir1Type is not swEndConditions_e.swEndCondMidPlane |
| 9 | `Dir1Angle` | `system.double` | Angle in radians of revolution in direction 1; only applies if Dir1Type is swEndConditions_e.swEndCondBlind |
| 10 | `Dir2Angle` | `system.double` | Angle in radians of revolution in direction 2; only applies if Dir2Type is swEndConditions_e.swEndCondBlind |
| 11 | `OffsetReverse1` | `system.bool` | True to reverse the offset direction in direction 1, false to not; only applies if Dir1Type is swEndConditions_e.swEndCondOffsetFromSurface |
| 12 | `OffsetReverse2` | `system.bool` | True to reverse the offset direction in direction 2, false to not; only applies if Dir2Type is swEndConditions_e.swEndCondOffsetFromSurface |
| 13 | `OffsetDistance1` | `system.double` | Offset distance in direction 1; only applies if Dir1Type is swEndConditions_e.swEndCondOffsetFromSurface |
| 14 | `OffsetDistance2` | `system.double` | Offset distance in direction 2; only applies if Dir2Type is swEndConditions_e.swEndCondOffsetFromSurface |
| 15 | `ThinType` | `system.int` | Type and direction as defined in swThinWallType_e |
| 16 | `ThinThickness1` | `system.double` | Wall thickness in direction 1 (if ThinType is swThinWallType_e.swThinWallMidPlane, (ThinThickness1)/2 is used for each direction) |
| 17 | `ThinThickness2` | `system.double` | Wall thickness in direction 2 (only applies if ThinType is swThinWallType_e.swThinWallTwoDirection) |
| 18 | `Merge` | `system.bool` | True to merge the results into a multi-body part, false to not |
| 19 | `UseFeatScope` | `system.bool` | True if the feature only affects selected bodies, false if the feature affects all bodies (see Remarks) |
| 20 | `UseAutoSelect` | `system.bool` | True to automatically select all bodies and have the feature affect those bodies, false to select the bodies or components that the feature affects (see Remarks) |

**Returns:** `Feature`

**Availability:** SOLIDWORKS 2011 FCS, Revision Number 19.0

### `IFeatureManager.InsertFeatureChamfer`

Inserts a chamfer.

**Args (8):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Options` | `system.int` | Options as defined by swFeatureChamferOption_e |
| 2 | `ChamferType` | `system.int` | Chamfer type as defined by swChamferType_e |
| 3 | `Width` | `system.double` | If ChamferType is swChamferAngleDistance, then specify width of chamfer |
| 4 | `Angle` | `system.double` | If ChamferType is swChamferAngleDistance, then specify the angle of the }}-->}}-->chamfer |
| 5 | `OtherDist` | `system.double` | If ChamferType is swChamferEqualDistance, then you can specify a single value so that all distances are equal |
| 6 | `VertexChamDist1` | `system.double` | If ChamferType is swChamferDistanceDistance or swChamferVertex, then specify a value for the distance on first side |
| 7 | `VertexChamDist2` | `system.double` | If ChamferType is swChamferDistanceDistance or swChamferVertex, then specify a value for the distance on second side |
| 8 | `VertexChamDist3` | `system.double` | If ChamferType is swChamferVertex, then specify a value for the distance on third side |

**Returns:** `Feature`

**Availability:** SOLIDWORKS 2005 FCS, Revision Number 13.0

### `IFeatureManager.InsertMirrorFeature2`

Mirrors selected features, faces, bodies, and structure systems about a selected plane or planar face.

**Args (5):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `BMirrorBody` | `system.bool` | True to mirror solid bodies; false to mirror a feature or face |
| 2 | `BGeometryPattern` | `system.bool` | True to mirror only the feature geometry, false to solve the entire feature; applies to mirroring features only |
| 3 | `BMerge` | `system.bool` | True to merge any mirrored solid bodies, false to not; applies to mirroring solid bodies only |
| 4 | `BKnit` | `system.bool` | True to knit surfaces, false to not; applies to mirroring surfaces only |
| 5 | `ScopeOptions` | `system.int` | Feature scope as defined by swFeatureScope_e |

**Returns:** `Feature`

**Availability:** SOLIDWORKS 2008 FCS, Revision Number 16.0

### `IFeatureManager.SimpleHole2`

Inserts a simple hole feature.

**Args (23):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Dia` | `system.double` | Hole diameter |
| 2 | `Sd` | `system.bool` | True for single-ended, false for double-ended |
| 3 | `Flip` | `system.bool` | True to flip the direction to cut, false to not |
| 4 | `Dir` | `system.bool` | True to flip direction to extrude, false to not |
| 5 | `T1` | `system.int` | Termination type for first end as defined in swEndConditions_e |
| 6 | `T2` | `system.int` | Termination type for second end as defined in swEndConditions_e |
| 7 | `D1` | `system.double` | Depth of extrusion for first end in meters |
| 8 | `D2` | `system.double` | Depth of extrusion for second end in meters |
| 9 | `Dchk1` | `system.bool` | True allows draft angle in first direction, false does not allow drafting |
| 10 | `Dchk2` | `system.bool` | True allows draft angle in second direction, false does not allow drafting |
| 11 | `Ddir1` | `system.bool` | For first draft angle to be inward use true, for draft angle outward use false |
| 12 | `Ddir2` | `system.bool` | For second draft angle to be inward use true, for draft angle outward use false |
| 13 | `Dang1` | `system.double` | Draft angle for first end |
| 14 | `Dang2` | `system.double` | Draft angle for second end |
| 15 | `OffsetReverse1` | `system.bool` | If you chose to offset the first end condition from another face or plane, then true specifies offset in direction away from the sketch, false specifies offset from the face or plane in a direction... |
| 16 | `OffsetReverse2` | `system.bool` | If you chose to offset the second end condition from another face or plane, then true specifies offset in direction away from the sketch, false specifies offset from the face or plane in a directio... |
| 17 | `TranslateSurface1` | `system.bool` | True to use an offset relative to the surface or the plane selected, false to use a true offset |
| 18 | `TranslateSurface2` | `system.bool` | True to use an offset relative to the surface or the plane selected, false to use a true offset |
| 19 | `UseFeatScope` | `system.bool` | True if the feature only affects selected bodies, false if the feature affects all bodies |
| 20 | `UseAutoSelect` | `system.bool` | True to automatically select all bodies and have the feature affect those bodies, false to select the bodies the feature affects |
| 21 | `AssemblyFeatureScope` | `system.bool` | True if the assembly feature only affects selected components in the assembly, false if the assembly feature affects all components in the assembly |
| 22 | `AutoSelectComponents` | `system.bool` | True to auto-select all affected components, false to not (use the selected components only) |
| 23 | `PropagateFeatureToParts` | `system.bool` | True to propagate the assembly feature to the components in the model that it affects, false to not |

**Returns:** `Feature`

**Availability:** SOLIDWORKS 2009 FCS, Revision Number 17.0

### `IGearMateFeatureData.EntitiesToMate`

Gets or sets the entities to mate in this gear mate.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2019 FCS, Revision Number 27.0

### `IGearMateFeatureData.GearRatioDenominator`

Gets or sets the denominator of the gear ratio of this gear mate.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2019 FCS, Revision Number 27.0

### `IGearMateFeatureData.GearRatioNumerator`

Gets or sets the numerator of the gear ratio of this gear mate.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2019 FCS, Revision Number 27.0

### `IGearMateFeatureData.Reverse`

Gets or sets whether to change the direction of rotation of the gears relative to one another in this gear mate.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2019 FCS, Revision Number 27.0

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

### `ISketchManager.CreateCenterLine`

Creates a center line between the specified points.

**Args (6):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `X1` | `system.double` | X coordinate of first end point, in meters |
| 2 | `Y1` | `system.double` | Y coordinate of first end point, in meters |
| 3 | `Z1` | `system.double` | Z coordinate of first end point, in meters |
| 4 | `X2` | `system.double` | X coordinate of second end point, in meters |
| 5 | `Y2` | `system.double` | Y coordinate of second end point, in meters |
| 6 | `Z2` | `system.double` | Z coordinate of second end point, in meters |

**Returns:** `SketchSegment`

**Availability:** SOLIDWORKS 2008 FCS, Revision Number 16.0

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

### `ISweepFeatureData.AccessSelections`

Accesses the selections that define this sweep feature.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `TopDoc` | `system.object` | Top-level document |
| 2 | `Component` | `system.object` | Component in which the feature is to be modified |

**Returns:** `System.bool`

**Availability:** SOLIDWORKS 2003 FCS, Revision Number 11.0

### `ISweepFeatureData.AdvancedSmoothing`

Gets or sets whether to apply advanced smoothing to this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.AlignWithEndFaces`

Gets or sets whether to align this sweep with the end faces.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.AssemblyFeatureScope`

Gets and sets whether this swept-cut feature affects only selected components in the assembly.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2011 FCS, Revision Number 19.0

### `ISweepFeatureData.AutoSelect`

Gets or sets whether to automatically select all bodies in a multibody part to be affected by this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2003 FCS, Revision Number 11.0

### `ISweepFeatureData.AutoSelectComponents`

Gets and sets whether to automatically select all assembly components to be affected by this swept-cutfeature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2011 FCS, Revision Number 19.0

### `ISweepFeatureData.CircularProfile`

Gets or sets whether to use a circular profile for this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2017 FCS, Revision Number 25.0

### `ISweepFeatureData.CircularProfileDiameter`

Gets or sets the diameter of the circular profile for this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2017 FCS, Revision Number 25.0

### `ISweepFeatureData.D1ReverseTwistDir`

Gets or sets whether to reverse the twist of this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2018 FCS, Revision Number 26.0

### `ISweepFeatureData.D2ReverseTwistDir`

Gets or sets whether to reverse the twist in Direction 2 of this bidirectional sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2018 FCS, Revision Number 26.0

### `ISweepFeatureData.Direction`

Gets or sets the direction type of this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2017 FCS, Revision Number 25.0

### `ISweepFeatureData.EndDirectionVector`

Obsolete. Gets or sets the direction vector in which to end this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.EndTangencyType`

Gets or sets tangency at the end of the sweep path of this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.FeatureScope`

Gets or sets whether to use scope in a multibody part for this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2003 FCS, Revision Number 11.0

### `ISweepFeatureData.FeatureScopeBodies`

Gets or sets the solid bodies in a multibody part affected by this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2003 FCS, Revision Number 11.0

### `ISweepFeatureData.GetCutSweepOption`

Gets the type of this cut sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.int`

**Availability:** SOLIDWORKS 2011 FCS, Revision Number 19.0

### `ISweepFeatureData.GetD2TwistAngle`

Gets the twist angle in Direction 2 of this bidirectional sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.double`

**Availability:** SOLIDWORKS 2018 FCS, Revision Number 26.0

### `ISweepFeatureData.GetFeatureScopeBodiesCount`

Gets the number of solid bodies affected by the sweep feature in a multibody part.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.int`

**Availability:** SOLIDWORKS 2003 FCS, Revision Number 11.0

### `ISweepFeatureData.GetGuideCurvesCount`

Gets a number of guide curves for this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.short`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.GetGuideCurvesType`

Gets the type of guide curves in this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.object`

**Availability:** SOLIDWORKS 2001Plus SP3, Revision Number 10.3

### `ISweepFeatureData.GetPathAlignmentDirectionVector`

Gets the direction vector of the specified type for this sweep feature.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Type` | `system.int` | Type of direction vector as defined in swSelectType_e: swSelDATAMAXES (axis) swSelDATUMPLANES (plane) swSelEDGES (edge) swSelFACES (face) |

**Returns:** `System.object`

**Availability:** SOLIDWORKS 2005 FCS, Revision Number 13.0

### `ISweepFeatureData.GetPathType`

Gets the path type for this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.int`

**Availability:** SOLIDWORKS 2001Plus SP2, Revision Number 10.2

### `ISweepFeatureData.GetProfileType`

Gets the profile type of this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.int`

**Availability:** SOLIDWORKS 2018 FCS, Revision Number 26.0

### `ISweepFeatureData.GetTwistAngle`

Gets the angle at which to twist this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.double`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.1

### `ISweepFeatureData.GetWallThickness`

Gets the wall thickness, forward (Direction 1) or reverse (Direction 2), of this thin-walled sweep feature.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Forward` | `system.bool` | True for Direction 1, false for Direction 2 |

**Returns:** `System.double`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.1

### `ISweepFeatureData.GuideCurves`

Gets or sets the guide curves for this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.IAccessSelections`

Obsolete. Accesses the selections that define this sweep feature.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `TopDoc` | `modeldoc2` | Top-level document |
| 2 | `Component` | `component2` | Component in which the feature is to be modified |

**Returns:** `System.bool`

**Availability:** SOLIDWORKS 2003 FCS, Revision Number 11.0

### `ISweepFeatureData.IGetFeatureScopeBodies`

Obsolete. Gets the solid bodies that the sweep feature affects in a multibody part.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Count` | `system.int` | Number of solid bodies to affect |

**Returns:** `Body2`

**Availability:** SOLIDWORKS 2003 FCS, Revision Number 11.0

### `ISweepFeatureData.IGetGuideCurves`

Obsolete. Gets the guide curves for this sweep feature.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Count` | `system.short` | Number of guide curves |

**Returns:** `System.object`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.1

### `ISweepFeatureData.IGetGuideCurvesType`

Obsolete. Gets the guide curve types for this sweep feature.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Count` | `system.int` | Number of guide curves |

**Returns:** `System.int`

**Availability:** SOLIDWORKS 2001Plus SP3, Revision Number 10.3

### `ISweepFeatureData.IsBossFeature`

Gets whether the sweep feature is a boss feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.bool`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.IsThinFeature`

Gets whether this is a thin-walled sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.bool`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.MaintainTangency`

Gets or sets whether to merge tangent faces in this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.Merge`

Gets or sets whether to merge the results of this swept-boss feature for a multibody part.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2003 FCS, Revision Number 11.0

### `ISweepFeatureData.MergeSmoothFaces`

Gets or sets whether to merge the smooth faces of this sweep feature that uses guide curves.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2003 FCS, Revision Number 11.0

### `ISweepFeatureData.Path`

Gets or sets the sweep path for this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.PathAlignmentType`

Gets or sets the alignment of the sweep path in this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2005 FCS, Revision Number 13.0

### `ISweepFeatureData.Profile`

Gets and sets the sketch profile or tool body for this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.PropagateFeatureToParts`

Gets and sets whether to extend the swept-cut feature to all affected parts in the assembly.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2011 FCS, Revision Number 19.0

### `ISweepFeatureData.ReleaseSelectionAccess`

Releases access to the selections for this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `void`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.SetD2TwistAngle`

Sets the twist angle in Direction 2 of this bidirectional sweep feature.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Angle` | `system.double` | Angle of twist in radians in Direction 2 |

**Returns:** `void`

**Availability:** SOLIDWORKS 2018 FCS, Revision Number 26.0

### `ISweepFeatureData.SetPathAlignmentDirectionVector`

Sets the direction vector for path alignment in this sweep feature.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Dir` | `system.object` | Plane, planar face, line, edge, cylinder, axis, or a pair of vertices that defines the direction |

**Returns:** `void`

**Availability:** SOLIDWORKS 2005 FCS, Revision Number 13.0

### `ISweepFeatureData.SetTwistAngle`

Sets the angle at which to twist this sweep feature.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Angle` | `system.double` | Angle of twist in radians |

**Returns:** `void`

**Availability:** SOLIDWORKS 2005 FCS, Revision Number 13.0

### `ISweepFeatureData.SetWallThickness`

Sets the wall thickness, forward (Direction 1) or reverse (Direction 2), of this thin-walled sweep feature.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Forward` | `system.bool` | True for Direction 1, false for Direction 2 (see Remarks) |
| 2 | `WallThickness` | `system.double` | Wall thickness |

**Returns:** `void`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.StartDirectionVector`

Obsolete. Gets or sets the direction vector in which to start this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.StartTangencyType`

Gets and sets the tangency at the start of the sweep path for this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.SweepType`

Gets the type of this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2018 FCS, Revision Number 26.0

### `ISweepFeatureData.TangentPropagation`

Gets or sets whether to propagate the sweep to the next tangent edge for this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.ThinFeature`

Gets or sets whether to make this sweep feature a thin-walled feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2018 FCS, Revision Number 26.0

### `ISweepFeatureData.ThinWallType`

Gets or sets the type of this thin-walled sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `ISweepFeatureData.TwistControlType`

Gets or sets the type of twist control for this sweep feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IVariableFilletFeatureData2.AccessSelections`

Gains access to the selections used to define the variable fillet feature.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `TopDoc` | `system.object` | Top-level document |
| 2 | `Component` | `system.object` | Component in which the feature is to be modified |

**Returns:** `System.bool`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IVariableFilletFeatureData2.AsymmetricFillet`

Gets or sets whether this variable radius fillet is asymmetric.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2015 FCS, Revision Number 23.0

### `IVariableFilletFeatureData2.ConicTypeForCrossSectionProfile`

Gets or sets the type of profile for this fillet.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2014 FCS, Revision Number 22.0

### `IVariableFilletFeatureData2.CurvatureContinuous`

Gets or sets whether to create a smoother curvature between adjacent surfaces for this variable radius fillet feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2016 FCS, Revision Number 24.0

### `IVariableFilletFeatureData2.DefaultConicRhoOrRadius`

Gets or sets the default conic rho or conic radius of this fillet.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2014 FCS, Revision Number 22.0

### `IVariableFilletFeatureData2.DefaultDistance`

Gets or sets the default Distance 2 radius of this asymmetric fillet.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2015 FCS, Revision Number 23.0

### `IVariableFilletFeatureData2.DefaultRadius`

Gets or sets the default radius for this symmetric fillet or the default Distance 1 radius for this asymmetric fillet.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IVariableFilletFeatureData2.FilletEdgeCount`

Gets the number of edges to fillet.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IVariableFilletFeatureData2.GetConicRhoOrRadius`

Gets the conic rho, conic radius, or circular radius of this fillet.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `PFilletItem` | `system.object` | Fillet edge for which to get a value (see Remarks) |

**Returns:** `System.double`

**Availability:** SOLIDWORKS 2014 FCS, Revision Number 22.0

### `IVariableFilletFeatureData2.GetConicRhoOrRadius2`

Gets the conic rho or radius at the specified vertex.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `PFilletItem` | `vertex` | Vertex for which to get a value (see Remarks) |
| 2 | `IsAssigned` | `system.bool` | True if the conic value is assigned to each control point, false if not |

**Returns:** `System.double`

**Availability:** SOLIDWORKS 2014 FCS, Revision Number 22.0

### `IVariableFilletFeatureData2.GetControlPointConicRhoOrRadiusAtIndex`

Gets the conic rho or radius at the specified control point.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Index` | `system.int` | Zero-based index of the control point (see Remarks) |

**Returns:** `System.double`

**Availability:** SOLIDWORKS 2014 FCS, Revision Number 22.0

### `IVariableFilletFeatureData2.GetControlPointDistanceAtIndex`

Gets the Distance 2 radius at the specified control point for the asymmetric fillet.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Index` | `system.int` | Zero-based index of control point for which to get the radius |

**Returns:** `System.double`

**Availability:** SOLIDWORKS 2015 FCS, Revision Number 23.0

### `IVariableFilletFeatureData2.GetControlPointRadiusAtIndex`

Gets the radius at the specified control point.

**Args (3):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Index` | `system.int` | Zero-based index of the control point |
| 2 | `Location` | `system.double` | Location of the control point |
| 3 | `PEdge` | `edge` | Edge |

**Returns:** `System.double`

**Availability:** SOLIDWORKS 2003 FCS, Revision Number 11.0

### `IVariableFilletFeatureData2.GetControlPointsCount`

Gets the number of intermediate control points on this variable fillet feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.int`

**Availability:** SOLIDWORKS 2003 FCS, Revision Number 11.0

### `IVariableFilletFeatureData2.GetDistance`

Gets the Distance 2 radius for this asymmetric fillet.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `PFilletItem` | `system.object` | Vertex at which to get the radius |

**Returns:** `System.double`

**Availability:** SOLIDWORKS 2015 FCS, Revision Number 23.0

### `IVariableFilletFeatureData2.GetFilletEdgeAtIndex`

Gets the fillet edge at the specified index.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Index` | `system.int` | Zero-based index of the fillet edge |

**Returns:** `System.object`

**Availability:** SOLIDWORKS 2000 FCS, Revision Number 8.0

### `IVariableFilletFeatureData2.GetRadius`

Obsolete. Superseded by IVariableFilletFeatureData2::GetRadius2.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `PFilletItem` | `system.object` |  |

**Returns:** `System.double`

### `IVariableFilletFeatureData2.GetRadius2`

Gets the value of the Distance 1 radius at the specified vertex.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `PFilletItem` | `vertex` | Vertex at which to get the radius |
| 2 | `IsAssigned` | `system.bool` | True if the radius is assigned to a control point, false if not |

**Returns:** `System.double`

**Availability:** SOLIDWORKS 2003 FCS, Revision Number 11.0

### `IVariableFilletFeatureData2.GetSetbackDistanceCount`

Gets the number of setback distances for the specified vertex on this variable fillet feature.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Vtx` | `vertex` | Vertex |

**Returns:** `System.int`

**Availability:** SOLIDWORKS 2004 FCS, Revision Number 12.0

### `IVariableFilletFeatureData2.GetSetbackVertexDistance`

Gets the setback distance for the specified vertex on this variable fillet feature.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Vtx` | `system.object` | Vertex for which to get setback distance |
| 2 | `EdgeVar` | `system.object` | Array of edges at the specified vertex (see Remarks) |

**Returns:** `System.object`

**Availability:** SOLIDWORKS 2004 FCS, Revision Number 12.0

### `IVariableFilletFeatureData2.GetSetbackVertices`

Gets the setback vertices for this variable fillet feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.object`

**Availability:** SOLIDWORKS 2004 FCS, Revision Number 12.0

### `IVariableFilletFeatureData2.GetSetbackVerticesCount`

Gets the number of setback vertices for this variable fillet feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `System.int`

**Availability:** SOLIDWORKS 2004 FCS, Revision Number 12.0

### `IVariableFilletFeatureData2.IAccessSelections`

Gains access to the selections used to define the variable fillet feature.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `TopDoc` | `modeldoc2` | Top-level document |
| 2 | `Component` | `component2` | Component in which the feature is to be modified |

**Returns:** `System.bool`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IVariableFilletFeatureData2.IGetConicRhoOrRadius`

Gets the conic rho, conic radius, or circular radius of this fillet.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `PFilletItem` | `vertex` | Fillet edge for which to get a value (see Remarks) |

**Returns:** `System.double`

**Availability:** SOLIDWORKS 2014 FCS, Revision Number 22.0

### `IVariableFilletFeatureData2.IGetFilletEdgeAtIndex`

Gets the fillet edge at the specified index.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Index` | `system.int` | Index at which fillet edge is required |

**Returns:** `Edge`

**Availability:** SOLIDWORKS 2000 FCS, Revision Number 8.0

### `IVariableFilletFeatureData2.IGetRadius`

Obsolete. Superseded by IVariableFilletFeatureData2::Radius2.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `PFilletItem` | `vertex` |  |

**Returns:** `System.double`

### `IVariableFilletFeatureData2.IGetSetbackVertexDistance`

Gets the setback distance for the specified vertex on this variable fillet feature.

**Args (3):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Count` | `system.int` | Number of edges and setback distances for this vertex |
| 2 | `Vtx` | `vertex` | Vertex for which to get setback distance |
| 3 | `EdgeArr` | `edge` | in-process, unmanaged C++: Pointer to an array of edges at the specified vertex (see Remarks) VBA, VB.NET, C#, and C++/CLI: Not supported See In-process Methods for details about this type of method. |

**Returns:** `System.double`

**Availability:** SOLIDWORKS 2004 FCS, Revision Number 12.0

### `IVariableFilletFeatureData2.IGetSetbackVertices`

Gets the setback vertices for this variable fillet feature.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Count` | `system.int` | Number of setback vertices |

**Returns:** `Vertex`

**Availability:** SOLIDWORKS 2004 FCS, Revision Number 12.0

### `IVariableFilletFeatureData2.ISetConicRhoOrRadius`

Sets the conic rho, conic radius, or circular radius of this fillet.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `PFilletItem` | `vertex` | Fillet edge for which to set ConicRhoVal (see Remarks) |
| 2 | `ConicRhoVal` | `system.double` | Conic rho, conic radius, or circular radius (see Remarks) |

**Returns:** `void`

**Availability:** SOLIDWORKS 2014 FCS, Revision Number 22.0

### `IVariableFilletFeatureData2.ISetRadius`

Sets the radius value for specified fillet item.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `PFilletItem` | `vertex` | Vertex whose radius to set |
| 2 | `Radius` | `system.double` | Radius |

**Returns:** `void`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IVariableFilletFeatureData2.ISetSetbackVertexDistance`

Sets the setback distance for the specified vertex and its edges on this variable fillet feature.

**Args (4):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Count` | `system.int` | Number of setback distances |
| 2 | `Vtx` | `vertex` | Vertex for which to set the setback distance |
| 3 | `EdgeArr` | `edge` | in-process, unmanaged C++: Pointer to an array of edges at the specified vertex (see Remarks) VBA, VB.NET, C#, and C++/CLI: Not supported See In-process Methods for details about this type of method. |
| 4 | `DistArr` | `system.double` | in-process, unmanaged C++: Pointer to an array of setback distances at the specified VBA, VB.NET, C#, and C++/CLI: Not supported |

**Returns:** `System.bool`

**Availability:** SOLIDWORKS 2004 FCS, Revision Number 12.0

### `IVariableFilletFeatureData2.ISetSetbackVertices`

Sets the setback vertices for this variable fillet feature.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Count` | `system.int` | Number of vertices |
| 2 | `VertArr` | `vertex` | in-process, unmanaged C++: Pointer to an array of setback vertices VBA, VB.NET, C#, and C++/CLI: Not supported See In-process Methods for details about this type of method. |

**Returns:** `System.bool`

**Availability:** SOLIDWORKS 2004 FCS, Revision Number 12.0

### `IVariableFilletFeatureData2.OverflowType`

Gets or sets the overflow type for this variable fillet feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IVariableFilletFeatureData2.PropagateFeatureToParts`

Gets or sets whether to extend the fillet feature to all affected parts in the assembly.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2011 FCS, Revision Number 19.0

### `IVariableFilletFeatureData2.PropagateToTangentFaces`

Gets or sets whether to extend the fillet to all faces tangent to the selected face or edge.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IVariableFilletFeatureData2.ReleaseSelectionAccess`

Releases access to the selections used to define the variable fillet feature.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Returns:** `void`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IVariableFilletFeatureData2.SetConicRhoOrRadius`

Sets the conic rho or radius for the specified fillet item.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `PFilletItem` | `system.object` | Fillet item for which to set ConicRhoVal (see Remarks) |
| 2 | `ConicRhoVal` | `system.double` | Conic rho or radius (see Remarks) |

**Returns:** `void`

**Availability:** SOLIDWORKS 2014 FCS, Revision Number 22.0

### `IVariableFilletFeatureData2.SetControlPointConicRhoOrRadiusAtIndex`

Sets the conic rho or radius at the specified control point.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Index` | `system.int` | Zero-based index of the control point for which to set ConicRhoVal (see Remarks) |
| 2 | `ConicRhoVal` | `system.double` | Conic rho or radius (see Remarks) |

**Returns:** `void`

**Availability:** SOLIDWORKS 2014 FCS, Revision Number 22.0

### `IVariableFilletFeatureData2.SetControlPointDistanceAtIndex`

Sets the Distance 2 radius at the specified control point for the asymmetric fillet.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Index` | `system.int` | Zero-based index of control point whose radius to set |
| 2 | `Dist2` | `system.double` | Distance 2 radius for the control point of this asymmetric fillet |

**Returns:** `void`

**Availability:** SOLIDWORKS 2015 FCS, Revision Number 23.0

### `IVariableFilletFeatureData2.SetControlPointRadiusAtIndex`

Sets the radius at the specified control point.

**Args (3):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Index` | `system.int` | Zero-based index of control point whose radius to set |
| 2 | `Location` | `system.double` | Percent distance between the edge start vertex and the edge end vertex |
| 3 | `Radius` | `system.double` | Value of the radius for the control point of this symmetric fillet; Distance 1 radius for the control point of this asymmetric fillet |

**Returns:** `void`

**Availability:** SOLIDWORKS 2003 FCS, Revision Number 11.0

### `IVariableFilletFeatureData2.SetDistance`

Sets the Distance 2 radius for this asymmetric fillet.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `PFilletItem` | `system.object` | Vertex at which to set the Distance 2 radius |
| 2 | `Dist2` | `system.double` | Distance 2 radius at the vertex specified by PFilletItem |

**Returns:** `void`

**Availability:** SOLIDWORKS 2015 FCS, Revision Number 23.0

### `IVariableFilletFeatureData2.SetRadius`

Sets the value of the Distance 1 radius at the specified vertex.

**Args (2):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `PFilletItem` | `system.object` | Vertex at which to set the radius |
| 2 | `Radius` | `system.double` | Radius of the symmetric fillet at the vertex specified by PFilletItem; Distance 1 radius of the asymmetric fillet at the vertex |

**Returns:** `void`

**Availability:** SOLIDWORKS 2001Plus FCS, Revision Number 10.0

### `IVariableFilletFeatureData2.SetSetbackVertexDistance`

Sets the setback distances on fillet edges from the specified fillet corner vertex on this variable fillet feature.

**Args (3):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `Vtx` | `system.object` | Vertex for which to set the setback distance |
| 2 | `EdgeVar` | `system.object` | Array of edges for this vertex |
| 3 | `DistVar` | `system.object` | Array of distances |

**Returns:** `System.bool`

**Availability:** SOLIDWORKS 2004 FCS, Revision Number 12.0

### `IVariableFilletFeatureData2.SetSetbackVertices`

Sets the setback vertices for this variable fillet feature.

**Args (1):**

| # | Name | Type | Description |
|---|------|------|-------------|
| 1 | `VertVar` | `system.object` | Array of vertices |

**Returns:** `System.bool`

**Availability:** SOLIDWORKS 2004 FCS, Revision Number 12.0

### `IVariableFilletFeatureData2.TransitionType`

Gets or sets the type of transition between this variable fillet and an adjacent fillet.

**Args (0):**

| # | Name | Type | Description |
|---|------|------|-------------|

**Availability:** SOLIDWORKS 2007 FCS, Revision Number 15.0

## Enums

### `swChamferType_e`

Chamfer types.

| Name | Value | Doc |
|------|-------|-----|
| `swChamferAngleDistance` | `1` |  |
| `swChamferDistanceDistance` | `2` |  |
| `swChamferVertex` | `3` |  |
| `swChamferEqualDistance` | `16` |  |

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

### `swFeatureChamferOption_e`

Chamfer feature options. Bitmask.

| Name | Value | Doc |
|------|-------|-----|
| `swFeatureChamferFlipDirection` | `1` |  |
| `swFeatureChamferKeepFeature` | `2` |  |
| `swFeatureChamferTangentPropagation` | `4` |  |
| `swFeatureChamferPropagateFeatToParts` | `8` |  |

### `swFeatureScope_e`

Feature scope options.

| Name | Value | Doc |
|------|-------|-----|
| `swFeatureScope_AllBodies` | `0` | All of the bodies in the multibody part are affected by the Mirror feature. |
| `swFeatureScope_SelectedBodiesWithAutoSelect` | `1` | Only the specified bodies in the multibody part are affected by the Mirror feature when AutoSelect is true. |
| `swFeatureScope_SelectedBodiesWithOutAutoSelect` | `2` | Only the specified bodies in the multibody part are affected by the Mirror feature when AutoSelect is false. |

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

### `swThinWallType_e`

Thin wall types.

| Name | Value | Doc |
|------|-------|-----|
| `swThinWallOneDirection` | `0` |  |
| `swThinWallOppDirection` | `1` |  |
| `swThinWallMidPlane` | `2` |  |
| `swThinWallTwoDirection` | `3` |  |

## Not found in CHM

- `method:IFeatureManager.FeatureCut5`
- `method:ISldWorks.SendKeys`
