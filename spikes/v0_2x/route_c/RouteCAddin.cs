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

        // The W66 experiment, end-to-end in-process: build a standalone planar
        // surface, select the sheet body, fire the exact 7-arg thicken that
        // ghosts OOP, and measure the volume/solid-body deltas.
        // W67 Track-2 hardening sweep: run the FULL flag matrix in ONE add-in
        // load — direction{side1=0,side2=1,both=2} x FillVolume{F,T} x
        // Merge{F,T} = 12 combos, each on its OWN fresh planar surface. If every
        // combo ghosts (dVol=0, no solid), "thicken is kernel-walled" becomes
        // absolute rather than "this one call is".
        private static void RunPayload(ISldWorks swApp, StringBuilder sb)
        {
            int[] dirs = { 0, 1, 2 };
            bool[] flags = { false, true };
            string template = swApp.GetUserPreferenceStringValue(
                (int)swUserPreferenceStringValue_e.swDefaultTemplatePart);
            bool anyPass = false;
            int combo = 0;
            foreach (int dir in dirs)
                foreach (bool fill in flags)
                    foreach (bool merge in flags)
                    {
                        combo++;
                        string tag = "COMBO" + combo + "[dir:" + dir + ",fill:" + fill + ",merge:" + merge + "]=";
                        try
                        {
                            IModelDoc2 model = swApp.NewDocument(template, 0, 0, 0) as IModelDoc2;
                            if (model == null) { sb.AppendLine(tag + "ERR:model null"); continue; }
                            model.SketchManager.InsertSketch(true);
                            model.SketchManager.CreateCornerRectangle(0, 0, 0, 0.04, 0.03, 0);
                            model.SketchManager.InsertSketch(true);
                            model.ClearSelection2(true);
                            model.Extension.SelectByID2("Sketch1", "SKETCH", 0, 0, 0, false, 0, null, 0);
                            model.InsertPlanarRefSurface();
                            model.ForceRebuild3(false);

                            Body2 sheet = FirstBody(model, swBodyType_e.swSheetBody);
                            if (sheet == null) { sb.AppendLine(tag + "ERR:no sheet body"); continue; }
                            sheet.Select2(false, null);

                            int solidsBefore = BodyCount(model, swBodyType_e.swSolidBody);
                            double volBefore = SolidVolM3(model);
                            object feat = model.FeatureManager.FeatureBossThicken(
                                0.002, dir, 0, fill, merge, false, true);
                            model.ForceRebuild3(false);
                            int solidsAfter = BodyCount(model, swBodyType_e.swSolidBody);
                            double volAfter = SolidVolM3(model);
                            int dSolids = solidsAfter - solidsBefore;
                            double dVol = (volAfter - volBefore) * 1e9;
                            bool pass = dSolids >= 1 && (volAfter - volBefore) > 0.0;
                            if (pass) anyPass = true;
                            sb.AppendLine(tag + "ret:" + (feat == null ? "null" : "nonnull")
                                + ",dsolids:" + dSolids + ",dvol:" + dVol.ToString("F4")
                                + ",pass:" + (pass ? "1" : "0"));
                        }
                        catch (Exception ex)
                        {
                            sb.AppendLine(tag + "ERR:" + ex.GetType().Name + ":" + ex.Message);
                        }
                    }
            sb.AppendLine("COMBOS=" + combo);
            sb.AppendLine("ANY_PASS=" + (anyPass ? "1" : "0"));
            sb.AppendLine("INPROC_PASS=" + (anyPass ? "1" : "0"));
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
