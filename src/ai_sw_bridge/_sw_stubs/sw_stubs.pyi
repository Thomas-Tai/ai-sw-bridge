"""Type stubs for SOLIDWORKS COM objects accessed via late binding.

These stubs describe the API surface actually exercised by ai-sw-bridge.
They exist so mypy can validate attribute-access patterns without requiring
a typelib (which SW's COM server does not expose via EnsureDispatch).

WHY LATE BINDING IS KEPT:
    SldWorks.Application cannot generate a typelib through
    win32com.client.gencache.EnsureDispatch ("this COM object can not
    automate the makepy process"). Every call goes through IDispatch::Invoke.
    This means: (1) zero-arg methods auto-invoke as properties on attribute
    access, (2) certain arg types (Callout, OUT params) can't be marshalled,
    (3) we use the legacy SelectByID (5 args) instead of SelectByID2 (9 args).
    See docs/known_gotchas.md for the full catalog.

CONVENTION:
    Properties that are actually zero-arg methods in the SW API are annotated
    as @property because pywin32 auto-invokes them on getattr. Writeable
    properties include a setter. Indexed method calls (e.g. eq.Equation(i))
    are annotated as __call__ on a descriptor.

These stubs are NOT installed as a package -- they're used for manual mypy
checks and IDE autocompletion. The actual runtime objects are CDispatch.
"""

from __future__ import annotations

from typing import Any, Protocol, Sequence

class _IndexAccessor(Protocol):
    """Indexed access like eq.Equation(i), eq.Value(i)."""

    def __call__(self, index: int) -> Any: ...

# --- ISldWorks ---

class ISldWorks:
    ActiveDoc: IModelDoc2 | None
    RevisionNumber: str

    def GetUserPreferenceStringValue(self, id: int) -> str: ...
    def GetUserPreferenceToggle(self, id: int) -> bool: ...
    def SetUserPreferenceToggle(self, id: int, value: bool) -> None: ...
    def NewDocument(
        self, template: str, paper_size: int, width: float, height: float
    ) -> IModelDoc2: ...
    def RunMacro(self, path: str, module: str, sub: str) -> int: ...
    def RunMacro2(self, path: str, module: str, sub: str, options: int) -> int: ...

# --- IModelDoc2 ---

class IModelDoc2:
    FeatureManager: IFeatureManager
    SketchManager: ISketchManager
    Extension: IModelDocExtension
    SelectionManager: ISelectionMgr
    GetPathName: str
    GetType: int
    GetTitle: str
    GetSaveFlag: bool
    EditRebuild3: bool
    ViewZoomtofit2: None
    GetEquationMgr: IEquationMgr
    FirstFeature: IFeature | None
    GetActiveSketch2: ISketch | None

    def ClearSelection2(self, all: bool) -> None: ...
    def SelectByID(
        self, name: str, type: str, x: float, y: float, z: float
    ) -> bool: ...
    def AddDimension2(self, x: float, y: float, z: float) -> Any: ...
    def FeatureByPositionReverse(self, index: int) -> IFeature: ...
    def SaveBMP(self, path: str, width: int, height: int) -> bool: ...
    def GetPartBox(self, cached: bool) -> tuple[float, ...]: ...
    def GetBodies2(self, body_type: int, visible_only: bool) -> tuple[IBody2, ...]: ...
    def Save(self) -> bool: ...
    def SaveAs3(self, name: str, version: int, options: int) -> tuple[int, int]: ...
    def EditSketch(self) -> None: ...
    def ForceRebuild3(self, top_level: bool) -> bool: ...

# --- IFeatureManager ---

class IFeatureManager:
    FirstFeature: IFeature | None

    def FeatureExtrusion2(self, *args: Any) -> IFeature | None: ...
    def FeatureCut4(self, *args: Any) -> IFeature | None: ...
    def FeatureRevolve2(self, *args: Any) -> IFeature | None: ...
    def SimpleHole2(self, *args: Any) -> IFeature | None: ...
    def CreateDefinition(self, feature_type: int) -> Any: ...
    def CreateFeature(self, data: Any) -> IFeature | None: ...
    def InsertFeatureChamfer(self, *args: Any) -> IFeature | None: ...
    def FeatureLinearPattern5(self, *args: Any) -> IFeature | None: ...
    def FeatureCircularPattern5(self, *args: Any) -> IFeature | None: ...
    def InsertMirrorFeature2(self, *args: Any) -> IFeature | None: ...

# --- ISketchManager ---

class ISketchManager:
    def InsertSketch(self, update: bool) -> None: ...
    def CreateCircle(
        self, cx: float, cy: float, cz: float, ex: float, ey: float, ez: float
    ) -> Any: ...
    def CreateCenterRectangle(
        self, cx: float, cy: float, cz: float, hx: float, hy: float, hz: float
    ) -> Any: ...
    def CreateCenterLine(
        self, x1: float, y1: float, z1: float, x2: float, y2: float, z2: float
    ) -> ISketchSegment | None: ...

# --- IModelDocExtension ---

class IModelDocExtension:
    CreateMassProperty: IMassProperty2
    GetEquationMgr: IEquationMgr

    def SelectByID2(
        self,
        name: str,
        type: str,
        x: float,
        y: float,
        z: float,
        append: bool,
        mark: int,
        callout: Any,
        option: int,
    ) -> bool: ...
    def RunCommand(self, cmd: int, prompt: str) -> Any: ...
    def GetMassProperties(
        self, accuracy: int, status: int
    ) -> Sequence[float] | None: ...

# --- IEquationMgr ---

class IEquationMgr:
    FilePath: str
    LinkToFile: bool
    AutomaticSolveOrder: bool
    AutomaticRebuild: bool
    Status: int
    GetCount: int
    Count: int
    UpdateValuesFromExternalEquationFile: bool

    def Equation(self, index: int) -> str: ...
    def Value(self, index: int) -> float: ...
    def GlobalVariable(self, index: int) -> bool: ...
    def Suppression(self, index: int) -> int: ...
    def Add2(self, index: int, formula: str, solve_order: int) -> int: ...

# --- IFeature ---

class IFeature:
    Name: str
    GetTypeName2: str
    GetTypeName: str
    GetErrorCode: int
    ErrorMessage: str
    IsSuppressed: bool
    GetNextFeature: IFeature | None
    GetFirstSubFeature: IFeature | None
    GetNextSubFeature: IFeature | None
    GetSpecificFeature2: Any

    def Select2(self, append: bool, mark: int) -> bool: ...

# --- ISelectionMgr ---

class ISelectionMgr:
    GetSelectedObjectCount2: int
    GetSelectedObjectCount: int

    def GetSelectedObjectsComponent4(self, index: int, mark: int) -> Any: ...
    def GetSelectedObjectType3(self, index: int, mark: int) -> int: ...
    def GetSelectedObject6(self, index: int, mark: int) -> Any: ...
    def SetSelectedObjectMark(self, index: int, mark: int, action: int) -> bool: ...

# --- IMassProperty2 ---

class IMassProperty2:
    Volume: float
    SurfaceArea: float
    Mass: float
    Density: float
    CenterOfMass: tuple[float, ...]

# --- IBody2 ---

class IBody2:
    def GetFaces(self) -> tuple[IFace2, ...]: ...
    def GetEdges(self) -> tuple[IEdge, ...]: ...

# --- IFace2 ---

class IFace2:
    Normal: tuple[float, ...]

    def GetClosestPointOn(self, x: float, y: float, z: float) -> tuple[float, ...]: ...
    def GetEdges(self) -> tuple[IEdge, ...]: ...
    def Select2(self, append: bool, mark: int) -> bool: ...

# --- IEdge ---

class IEdge:
    def GetClosestPointOn(self, x: float, y: float, z: float) -> tuple[float, ...]: ...
    def Select2(self, append: bool, mark: int) -> bool: ...

# --- ISketchSegment ---

class ISketchSegment:
    ConstructionGeometry: bool
    GetStartPoint2: ISketchPoint
    GetEndPoint2: ISketchPoint

    def Select4(self, append: bool, data: Any) -> bool: ...

# --- ISketchPoint ---

class ISketchPoint:
    X: float
    Y: float

# --- ISketch ---

class ISketch:
    RelationManager: ISketchRelationManager

# --- ISketchRelationManager ---

class ISketchRelationManager:
    def GetRelations(self, filter: int) -> tuple[ISketchRelation, ...]: ...
    def DeleteRelation(self, relation: ISketchRelation) -> bool: ...

# --- ISketchRelation ---

class ISketchRelation:
    GetRelationType: int

# --- ISimpleFilletFeatureData2 ---

class ISimpleFilletFeatureData2:
    DefaultRadius: float

    def Initialize(self, radius_type: int) -> None: ...
