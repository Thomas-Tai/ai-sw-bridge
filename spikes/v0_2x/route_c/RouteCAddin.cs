// W67 Track-2 / Route-C — Minimum Viable Add-in (ISwAddin).
//
// A formally-documented, production-grade in-process vehicle, after the VSTA
// RunMacro2 path proved to silently no-op a hand-compiled DLL. SOLIDWORKS
// CoCreates this COM class at startup and calls ConnectToSW IN ITS OWN PROCESS
// with a DIRECT ISldWorks pointer (no marshaling). We hijack ConnectToSW to run
// the entire W66 thicken experiment in-process and write the file sentinel.
//
// Register once (admin): RegAsm /codebase RouteCAddin.dll  -> writes HKCR COM
// keys + invokes RegisterFunction (HKLM Addins + HKCU AddInsStartup). Iterate
// by rebuild-in-place + SW restart; GUID/path fixed so no re-register needed.

using System;
using System.IO;
using System.Text;
using System.Runtime.InteropServices;
using Microsoft.Win32;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;
using SolidWorks.Interop.swpublished;

namespace RouteCAddin
{
    [Guid("C0FFEE00-1234-4567-89AB-FEEDFACE0001")]
    [ComVisible(true)]
    [ProgId("RouteCAddin.SwAddin")]
    public class SwAddin : ISwAddin
    {
        private static string SentinelPath()
        {
            return Path.Combine(Path.GetTempPath(), "route_c_sentinel.txt");
        }

        public bool ConnectToSW(object ThisSW, int Cookie)
        {
            StringBuilder sb = new StringBuilder();
            sb.AppendLine("MAIN_ENTERED=1");
            sb.AppendLine("ENTRY=addin_connect");
            try
            {
                ISldWorks swApp = ThisSW as ISldWorks;
                sb.AppendLine("SWAPP_NULL=" + (swApp == null));
                if (swApp != null)
                {
                    sb.AppendLine("SWAPP_REV=" + swApp.RevisionNumber());
                    RunPayload(swApp, sb);
                }
            }
            catch (Exception ex)
            {
                sb.AppendLine("ERR=" + ex.GetType().Name + ": " + ex.Message);
            }
            finally
            {
                try { File.WriteAllText(SentinelPath(), sb.ToString()); }
                catch { }
            }
            return true;
        }

        public bool DisconnectFromSW()
        {
            return true;
        }

        // W68 Route-C / wrap probe — InsertWrapFeature2 (5-arg) + Mode-A scan.
        // Fixture: cylinder + closed sketch near cylinder surface.
        // Gate: emboss(+vol)/deboss(-vol)/scribe(ΔFaces).
        private static void RunPayload(ISldWorks swApp, StringBuilder sb)
        {
            string template = swApp.GetUserPreferenceStringValue(
                (int)swUserPreferenceStringValue_e.swDefaultTemplatePart);
            try
            {
                IModelDoc2 model = swApp.NewDocument(template, 0, 0, 0) as IModelDoc2;
                if (model == null) { sb.AppendLine("ERR:model null"); return; }

                // --- CYLINDER (boss extrude circle on Top Plane) ---
                model.Extension.SelectByID2("Top Plane", "PLANE", 0, 0, 0, false, 0, null, 0);
                model.SketchManager.InsertSketch(true);
                model.SketchManager.CreateCircle(0, 0, 0, 0.02, 0, 0); // 20mm radius
                model.SketchManager.InsertSketch(true);
                model.ClearSelection2(true);
                model.Extension.SelectByID2("Sketch1", "SKETCH", 0, 0, 0, false, 0, null, 0);
                // Boss extrude 30mm
                model.FeatureManager.FeatureExtrusion2(
                    true, false, false,
                    0, 0,        // end conditions (blind, blind)
                    0.03, 0,     // depths
                    false, false, false, false,
                    0, 0,        // draft angles
                    false, false, false, false,
                    true, true, true,
                    0, 0, false);
                model.ForceRebuild3(false);

                Body2 body = FirstBody(model, swBodyType_e.swSolidBody);
                if (body == null) { sb.AppendLine("ERR:no cylinder body"); return; }
                int fBefore = GetFaceCount(body);
                double vBefore = SolidVolM3(model);
                sb.AppendLine("CYLINDER_FACES=" + fBefore + ",VOL_MM3=" + (vBefore * 1e9).ToString("F4"));

                // --- WRAP SKETCH on Front Plane ---
                // Small rectangle on the Front Plane, centered on the cylinder surface
                // Front Plane is XZ (Y=0). Cylinder surface is at radius 20mm from Z-axis.
                // Position the sketch rectangle at the cylinder surface.
                model.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, false, 0, null, 0);
                model.SketchManager.InsertSketch(true);
                // Small 5mm x 5mm rectangle centered at (0.02, 0, 0.015) in sketch coords
                model.SketchManager.CreateCornerRectangle(
                    0.0175, 0.0125, 0, 0.0225, 0.0175, 0);
                model.SketchManager.InsertSketch(true);
                model.ClearSelection2(true);

                // Get the cylindrical face (not the top/bottom flat faces)
                object[] faces = body.GetFaces() as object[];
                int faceCount = faces == null ? 0 : faces.Length;
                sb.AppendLine("BODY_FACES=" + faceCount);

                // Select sketch + face for wrap
                bool skSel = model.Extension.SelectByID2("Sketch2", "SKETCH", 0, 0, 0, false, 0, null, 0);
                // Also select a face (try the first face)
                if (faces != null && faces.Length > 0)
                {
                    Entity faceEnt = faces[0] as Entity;
                    try { if (faceEnt != null) faceEnt.Select2(true, 0); } catch { }
                }
                ISelectionMgr selMgr = model.SelectionManager as ISelectionMgr;
                int selCnt = selMgr != null ? selMgr.GetSelectedObjectCount() : -1;
                sb.AppendLine("WRAP_SEL=" + selCnt);

                // --- WRAP MATRIX ---
                int attempt = 0;
                bool anyPass = false;
                // Type: 0=emboss, 1=deboss, 2=scribe
                int[] types = { 0, 1, 2 };
                double thickness = 0.001; // 1mm

                foreach (int wrapType in types)
                {
                    attempt++;
                    Body2 fb = FirstBody(model, swBodyType_e.swSolidBody);
                    int fB = fb != null ? GetFaceCount(fb) : 0;
                    double vB = SolidVolM3(model);

                    object feat = null;
                    string err = "";
                    try {
                        feat = model.FeatureManager.InsertWrapFeature2(
                            wrapType,   // Type (emboss/deboss/scribe)
                            thickness,  // Thickness
                            false,      // ReverseDir
                            0,          // Method
                            50          // MeshFactor
                        );
                    } catch (Exception ex) { err = ex.GetType().Name + ":" + ex.Message.Substring(0, Math.Min(80, ex.Message.Length)); }
                    model.ForceRebuild3(false);

                    Body2 bA = FirstBody(model, swBodyType_e.swSolidBody);
                    int fA = bA != null ? GetFaceCount(bA) : 0;
                    double vA = SolidVolM3(model);
                    double dV = (vA - vB) * 1e9;
                    int dF = fA - fB;
                    bool pass = (feat != null) && (dF > 0 || Math.Abs(dV) > 0.001);
                    if (pass) anyPass = true;
                    sb.AppendLine("A" + attempt + "[type:" + wrapType
                        + "]=ret:" + (feat == null ? "null" : "nonnull")
                        + ",df:" + dF + ",dv:" + dV.ToString("F4")
                        + ",p:" + (pass ? "1" : "0")
                        + (err.Length > 0 ? ",err:" + err : ""));
                }

                // --- MODE-A: scan for IWrapSketchFeatureData ---
                int[] scanIds = { 65, 70, 75, 80, 85, 90, 95, 100, 110, 120 };
                foreach (int id in scanIds)
                {
                    if (anyPass) break;
                    attempt++;
                    object def2 = null;
                    string defErr = "";
                    try { def2 = model.FeatureManager.CreateDefinition(id); }
                    catch (Exception ex) { defErr = ex.GetType().Name; }

                    if (def2 == null) {
                        sb.AppendLine("A" + attempt + "[modeA,id:" + id + "]=def:null"
                            + (defErr.Length > 0 ? ",err:" + defErr : ""));
                        continue;
                    }

                    IWrapSketchFeatureData wf = def2 as IWrapSketchFeatureData;
                    if (wf == null) {
                        sb.AppendLine("A" + attempt + "[modeA,id:" + id + "]=def:ok,qi:null");
                        continue;
                    }

                    sb.AppendLine("A" + attempt + "[modeA,id:" + id + "]=WRAP_FOUND");
                    // Set properties and try to create
                    try {
                        wf.Type = 0; // emboss
                        wf.Thickness = 0.001;
                    } catch (Exception ex) {
                        sb.AppendLine("A" + attempt + "=setprop:err:" + ex.GetType().Name);
                        continue;
                    }

                    Body2 fb = FirstBody(model, swBodyType_e.swSolidBody);
                    int fB2 = fb != null ? GetFaceCount(fb) : 0;
                    double vB2 = SolidVolM3(model);

                    object feat2 = null;
                    string featErr = "";
                    try { feat2 = model.FeatureManager.CreateFeature(def2); }
                    catch (Exception ex) { featErr = ex.GetType().Name; }
                    model.ForceRebuild3(false);

                    Body2 bA2 = FirstBody(model, swBodyType_e.swSolidBody);
                    int fA2 = bA2 != null ? GetFaceCount(bA2) : 0;
                    double vA2 = SolidVolM3(model);
                    double dV2 = (vA2 - vB2) * 1e9;
                    bool pass2 = feat2 != null && (fA2 - fB2 > 0 || Math.Abs(dV2) > 0.001);
                    if (pass2) anyPass = true;
                    sb.AppendLine("A" + attempt + "[modeA,create]"
                        + "=ret:" + (feat2 == null ? "null" : "nonnull")
                        + ",df:" + (fA2 - fB2) + ",dv:" + dV2.ToString("F4")
                        + ",p:" + (pass2 ? "1" : "0")
                        + (featErr.Length > 0 ? ",err:" + featErr : ""));
                }

                sb.AppendLine("ATTEMPTS=" + attempt);
                sb.AppendLine("ANY_PASS=" + (anyPass ? "1" : "0"));
                sb.AppendLine("INPROC_PASS=" + (anyPass ? "1" : "0"));
            }
            catch (Exception ex)
            {
                sb.AppendLine("ERR=" + ex.GetType().Name + ": " + ex.Message);
            }
        }

        private static Body2 FirstBody(IModelDoc2 model, swBodyType_e t)
        {
            object[] b = Bodies(model, t);
            return (b == null || b.Length == 0) ? null : b[0] as Body2;
        }

        private static int BodyCount(IModelDoc2 model, swBodyType_e t)
        {
            object[] b = Bodies(model, t);
            return b == null ? 0 : b.Length;
        }

        private static object[] Bodies(IModelDoc2 model, swBodyType_e t)
        {
            IPartDoc part = model as IPartDoc;
            if (part == null) return null;
            return part.GetBodies2((int)t, true) as object[];
        }

        private static double SolidVolM3(IModelDoc2 model)
        {
            object[] bodies = Bodies(model, swBodyType_e.swSolidBody);
            if (bodies == null) return 0.0;
            double v = 0.0;
            foreach (object bo in bodies)
            {
                Body2 b = bo as Body2;
                if (b == null) continue;
                double[] mp = b.GetMassProperties(1.0) as double[];
                if (mp != null && mp.Length > 3) v += mp[3];
            }
            return v;
        }

        private static int GetFaceCount(Body2 body)
        {
            object[] faces = body.GetFaces() as object[];
            return faces == null ? 0 : faces.Length;
        }

        [ComRegisterFunction]
        public static void RegisterFunction(Type t)
        {
            string g = "{" + t.GUID.ToString().ToUpper() + "}";
            using (RegistryKey rk = Registry.LocalMachine.CreateSubKey(
                "SOFTWARE\\SOLIDWORKS\\Addins\\" + g))
            {
                rk.SetValue(null, 1, RegistryValueKind.DWord); // load by default
                rk.SetValue("Title", "RouteCAddin");
                rk.SetValue("Description", "W67 Route-C in-process thicken probe");
            }
            using (RegistryKey rk2 = Registry.CurrentUser.CreateSubKey(
                "Software\\SOLIDWORKS\\AddInsStartup\\" + g))
            {
                rk2.SetValue(null, 1, RegistryValueKind.DWord); // per-user enable
            }
        }

        [ComUnregisterFunction]
        public static void UnregisterFunction(Type t)
        {
            string g = "{" + t.GUID.ToString().ToUpper() + "}";
            try { Registry.LocalMachine.DeleteSubKeyTree("SOFTWARE\\SOLIDWORKS\\Addins\\" + g, false); }
            catch { }
            try { Registry.CurrentUser.DeleteSubKeyTree("Software\\SOLIDWORKS\\AddInsStartup\\" + g, false); }
            catch { }
        }
    }
}
