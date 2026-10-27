using UnityEditor;
using UnityEngine;
public static class BuildScript
{
    [MenuItem("Mobile/Build Android APK")]
    public static void BuildAndroid()
    {
        var opts = new BuildPlayerOptions
        {
            scenes = new[] { "Assets/Scenes/Level_01/Level_01_Main.unity" },
            locationPathName = "build/Android/fpssample.apk",
            target = BuildTarget.Android,
            options = BuildOptions.None
        };
        var r = BuildPipeline.BuildPlayer(opts);
        if (r.summary.result != UnityEditor.Build.Reporting.BuildResult.Succeeded)
            EditorApplication.Exit(1);
    }
}
