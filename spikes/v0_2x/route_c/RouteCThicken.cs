// W67 Track-2 / Route-C feasibility — in-process FeatureBossThicken payload.
//
// Run via ISldWorks.RunMacro2(dll, "SolidWorksMacro", "Main", ...). The SW
// VSTA host instantiates this class IN SOLIDWORKS' OWN PROCESS. For a genuine
// VSTA assembly it injects the running ISldWorks into `swApp`; a hand-compiled
// DLL gets Main() invoked but NO injection, so we fall back to
// Marshal.GetActiveObject (on SW's STA = a DIRECT in-process pointer).
//
// FEEDBACK CHANNEL = a FILE in %TEMP% (route_c_sentinel.txt), written as the
// FIRST action and independent of swApp — so even a null-app early-bail is
// reported. (Custom properties can't be the channel: they need the doc, which
// needs swApp — the very thing under test.)
//
// Compile (headless framework csc) — see build_route_c.ps1.

using System;
using System.Text;
using System.IO;
using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

public class SolidWorksMacro
{
    private static string SentinelPath()
    {
        return Path.Combine(Path.GetTempPath(), "route_c_sentinel.txt");
    }

    // Option-1 probe: STATIC entry. If RunMacro2 invokes a static Main, the
    // file sentinel appears; if not, the VSTA host needs a genuine scaffolded
    // assembly and we pivot to the COM add-in.
    public static void Main()
    {
        StringBuilder sb = new StringBuilder();
        sb.AppendLine("MAIN_ENTERED=1");
        sb.AppendLine("ENTRY=static");
        ISldWorks swApp = null;
        try
        {
            try
            {
                swApp = (ISldWorks)Marshal.GetActiveObject("SldWorks.Application");
                sb.AppendLine("SWAPP_SRC=getactiveobject");
            }
            catch (Exception ge) { sb.AppendLine("SWAPP_SRC=null(" + ge.Message + ")"); }
            sb.AppendLine("SWAPP_NULL=" + (swApp == null));

            if (swApp != null)
            {
                sb.AppendLine("SWAPP_REV=" + swApp.RevisionNumber());
                IModelDoc2 model = (IModelDoc2)swApp.ActiveDoc;
                sb.AppendLine("MODEL_NULL=" + (model == null));
                if (model != null)
                {
                    ISelectionMgr sm = (ISelectionMgr)model.SelectionManager;
                    int selCount = sm.GetSelectedObjectCount2(-1);
                    sb.AppendLine("SELCOUNT=" + selCount);
                    if (selCount == 0)
                    {
                        Body2 sb2 = FirstBody(model, swBodyType_e.swSheetBody);
                        if (sb2 != null) ((Entity)sb2).Select4(false, null);
                        sb.AppendLine("RESELECTED=" + (sb2 != null));
                    }

                    int solidsBefore = BodyCount(model, swBodyType_e.swSolidBody);
                    double volBefore = SolidVolM3(model);
                    sb.AppendLine("SOLIDS_BEFORE=" + solidsBefore);
                    sb.AppendLine("SHEETS_BEFORE=" + BodyCount(model, swBodyType_e.swSheetBody));

                    IFeatureManager fm = model.FeatureManager;
                    // The W66 OOP-ghosting shape, verbatim: Thickness=2mm,
                    // Direction=0(side1), FaceIndex=0, FillVolume=false,
                    // Merge=false, UseFeatScope=false, UseAutoSelect=true.
                    object feat = fm.FeatureBossThicken(0.002, 0, 0, false, false, false, true);
                    model.ForceRebuild3(false);

                    int solidsAfter = BodyCount(model, swBodyType_e.swSolidBody);
                    double volAfter = SolidVolM3(model);
                    double dVolMm3 = (volAfter - volBefore) * 1e9;
                    sb.AppendLine("THICKEN_RET=" + (feat == null ? "null" : "nonnull"));
                    sb.AppendLine("SOLIDS_AFTER=" + solidsAfter);
                    sb.AppendLine("SHEETS_AFTER=" + BodyCount(model, swBodyType_e.swSheetBody));
                    sb.AppendLine("DVOL_MM3=" + dVolMm3.ToString("F4"));
                    bool pass = (solidsAfter - solidsBefore) >= 1 && (volAfter - volBefore) > 0.0;
                    sb.AppendLine("INPROC_PASS=" + (pass ? "1" : "0"));
                }
            }
        }
        catch (Exception ex)
        {
            sb.AppendLine("ERR=" + ex.GetType().Name + ": " + ex.Message);
        }
        finally
        {
            try { File.WriteAllText(SentinelPath(), sb.ToString()); } catch { }
        }
    }

    private static Body2 FirstBody(IModelDoc2 model, swBodyType_e t)
    {
        object[] bodies = Bodies(model, t);
        if (bodies == null || bodies.Length == 0) return null;
        return bodies[0] as Body2;
    }

    private static int BodyCount(IModelDoc2 model, swBodyType_e t)
    {
        object[] bodies = Bodies(model, t);
        return bodies == null ? 0 : bodies.Length;
    }

    private static object[] Bodies(IModelDoc2 model, swBodyType_e t)
    {
        IPartDoc part = model as IPartDoc;
        if (part == null) return null;
        object raw = part.GetBodies2((int)t, true);
        return raw as object[];
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
}
