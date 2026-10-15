using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

/// <summary>
/// Imports Frameforge sheets (PNG + sibling JSON) into sliced sprites,
/// AnimationClips, and an AnimatorController. Auto-runs when a *_sheet.png
/// with a sibling JSON is imported under Assets/.
/// </summary>
public static class FrameforgeSheetImport
{
    const string DefaultOutputRoot = "Assets/Creatures/spritesheets";
    const string PendingFile = "Assets/Editor/Frameforge/pending-imports.txt";
    static bool _importing;

    [InitializeOnLoadMethod]
    static void ProcessPendingImports()
    {
        EditorApplication.delayCall += () =>
        {
            if (_importing || EditorApplication.isCompiling || EditorApplication.isUpdating)
            {
                return;
            }

            string abs = ToAbsolutePath(PendingFile);
            if (!File.Exists(abs))
            {
                return;
            }

            string[] lines = File.ReadAllLines(abs);
            File.Delete(abs);
            if (File.Exists(abs + ".meta"))
            {
                File.Delete(abs + ".meta");
            }

            foreach (string line in lines)
            {
                string path = (line ?? "").Trim().Replace('\\', '/');
                if (string.IsNullOrEmpty(path) || path.StartsWith("#"))
                {
                    continue;
                }

                try
                {
                    ImportAtPath(path);
                    Debug.Log($"Frameforge: pending import done for {path}");
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"Frameforge: pending import failed for {path}: {ex.Message}");
                }
            }

            AssetDatabase.Refresh();
        };
    }

    /// <summary>Queue a sheet for import after the next editor domain reload / compile.</summary>
    public static void EnqueueImport(string textureAssetPath)
    {
        textureAssetPath = (textureAssetPath ?? "").Trim().Replace('\\', '/');
        if (string.IsNullOrEmpty(textureAssetPath))
        {
            return;
        }

        EnsureFolder("Assets/Editor/Frameforge");
        string abs = ToAbsolutePath(PendingFile);
        var existing = File.Exists(abs)
            ? new HashSet<string>(File.ReadAllLines(abs), StringComparer.OrdinalIgnoreCase)
            : new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        existing.Add(textureAssetPath);
        File.WriteAllLines(abs, existing);
    }

    [Serializable]
    class SheetData
    {
        public string name;
        public int cellWidth;
        public int cellHeight;
        public int columns;
        public int rows;
        public int frameCount;
        public int pixelsPerUnit = 100;
        public AnimData[] animations;
    }

    [Serializable]
    class AnimData
    {
        public string name;
        public int[] frameIndices;
        public int fps = 8;
        public bool loop = true;
    }

    [MenuItem("Assets/Frameforge/Import Selected Sheet")]
    public static void ImportSelectedMenu()
    {
        var tex = Selection.activeObject as Texture2D;
        if (tex == null)
        {
            Debug.LogError("Frameforge: select a sheet Texture2D (*_sheet.png).");
            return;
        }

        string texPath = AssetDatabase.GetAssetPath(tex);
        try
        {
            var result = ImportAtPath(texPath);
            Debug.Log($"Frameforge: imported {result.CharacterName} → {result.OutputFolder} ({result.ClipPaths.Count} clips)");
        }
        catch (Exception ex)
        {
            Debug.LogError($"Frameforge: {ex.Message}");
        }
    }

    [MenuItem("Assets/Frameforge/Import Selected Sheet", true)]
    static bool ImportSelectedMenuValidate()
    {
        return Selection.activeObject is Texture2D;
    }

    /// <summary>
    /// Import a sheet texture asset path (Assets/.../*_sheet.png). JSON must sit next to it.
    /// </summary>
    public static ImportResult ImportAtPath(string textureAssetPath, string outputFolder = null)
    {
        if (string.IsNullOrWhiteSpace(textureAssetPath))
        {
            throw new ArgumentException("textureAssetPath is required");
        }

        textureAssetPath = textureAssetPath.Replace('\\', '/');
        var texture = AssetDatabase.LoadAssetAtPath<Texture2D>(textureAssetPath);
        if (texture == null)
        {
            throw new InvalidOperationException($"Texture not found at {textureAssetPath}");
        }

        string jsonAssetPath = Path.ChangeExtension(textureAssetPath, ".json").Replace('\\', '/');
        var jsonAsset = AssetDatabase.LoadAssetAtPath<TextAsset>(jsonAssetPath);
        string jsonText = jsonAsset != null ? jsonAsset.text : null;
        if (string.IsNullOrEmpty(jsonText))
        {
            string absJson = ToAbsolutePath(jsonAssetPath);
            if (File.Exists(absJson))
            {
                jsonText = File.ReadAllText(absJson);
            }
        }

        if (string.IsNullOrEmpty(jsonText))
        {
            throw new InvalidOperationException($"Sheet JSON missing next to texture: {jsonAssetPath}");
        }

        SheetData data = JsonUtility.FromJson<SheetData>(jsonText);
        if (data == null || data.cellWidth <= 0 || data.cellHeight <= 0)
        {
            throw new InvalidOperationException("Invalid sheet JSON (cellWidth/cellHeight).");
        }

        string stem = string.IsNullOrWhiteSpace(data.name)
            ? Path.GetFileNameWithoutExtension(textureAssetPath).Replace("_sheet", "")
            : data.name;
        string outFolder = string.IsNullOrWhiteSpace(outputFolder)
            ? $"{DefaultOutputRoot}/{stem}"
            : outputFolder.Replace('\\', '/').TrimEnd('/');

        bool prev = _importing;
        _importing = true;
        try
        {
            EnsureFolder(outFolder);

            var importer = AssetImporter.GetAtPath(textureAssetPath) as TextureImporter;
            if (importer == null)
            {
                throw new InvalidOperationException("TextureImporter missing.");
            }

            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Multiple;
            importer.filterMode = FilterMode.Point;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.mipmapEnabled = false;
            importer.spritePixelsPerUnit = data.pixelsPerUnit > 0 ? data.pixelsPerUnit : 100;

            var metas = new List<SpriteMetaData>();
            int count = Mathf.Max(data.frameCount, data.columns * Mathf.Max(data.rows, 1));
            for (int i = 0; i < count; i++)
            {
                int col = i % data.columns;
                int row = i / data.columns;
                float y = texture.height - (row + 1) * data.cellHeight;
                metas.Add(new SpriteMetaData
                {
                    name = $"{stem}_{i:00}",
                    rect = new Rect(col * data.cellWidth, y, data.cellWidth, data.cellHeight),
                    alignment = (int)SpriteAlignment.Center,
                    pivot = new Vector2(0.5f, 0.5f)
                });
            }

            importer.spritesheet = metas.ToArray();
            EditorUtility.SetDirty(importer);
            importer.SaveAndReimport();

            var byName = new Dictionary<string, Sprite>();
            foreach (var obj in AssetDatabase.LoadAllAssetsAtPath(textureAssetPath))
            {
                if (obj is Sprite sp)
                {
                    byName[sp.name] = sp;
                }
            }

            var clipPaths = new List<string>();
            AnimationClip defaultClip = null;
            if (data.animations != null)
            {
                foreach (var anim in data.animations)
                {
                    if (anim.frameIndices == null || anim.frameIndices.Length == 0)
                    {
                        continue;
                    }

                    var clip = new AnimationClip
                    {
                        frameRate = Mathf.Max(1, anim.fps),
                        name = anim.name,
                        wrapMode = anim.loop ? WrapMode.Loop : WrapMode.Once
                    };

                    var bindings = new EditorCurveBinding
                    {
                        type = typeof(SpriteRenderer),
                        path = "",
                        propertyName = "m_Sprite"
                    };

                    var keyframes = new ObjectReferenceKeyframe[anim.frameIndices.Length];
                    float dt = 1f / Mathf.Max(1, anim.fps);
                    for (int k = 0; k < anim.frameIndices.Length; k++)
                    {
                        int idx = anim.frameIndices[k];
                        string spriteName = $"{stem}_{idx:00}";
                        byName.TryGetValue(spriteName, out Sprite sprite);
                        keyframes[k] = new ObjectReferenceKeyframe
                        {
                            time = k * dt,
                            value = sprite
                        };
                    }

                    AnimationUtility.SetObjectReferenceCurve(clip, bindings, keyframes);
                    if (anim.loop)
                    {
                        var settings = AnimationUtility.GetAnimationClipSettings(clip);
                        settings.loopTime = true;
                        AnimationUtility.SetAnimationClipSettings(clip, settings);
                    }

                    string clipPath = $"{outFolder}/{stem}_{anim.name}.anim";
                    var existing = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
                    if (existing != null)
                    {
                        EditorUtility.CopySerialized(clip, existing);
                        EditorUtility.SetDirty(existing);
                        UnityEngine.Object.DestroyImmediate(clip);
                        clip = existing;
                    }
                    else
                    {
                        AssetDatabase.CreateAsset(clip, clipPath);
                    }

                    clipPaths.Add(clipPath);
                    if (defaultClip == null)
                    {
                        defaultClip = clip;
                    }
                }
            }

            string controllerPath = null;
            if (clipPaths.Count > 0)
            {
                controllerPath = $"{outFolder}/{stem}.controller";
                var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath);
                if (controller == null)
                {
                    controller = AnimatorController.CreateAnimatorControllerAtPath(controllerPath);
                }

                var sm = controller.layers[0].stateMachine;
                while (sm.states.Length > 0)
                {
                    sm.RemoveState(sm.states[0].state);
                }

                AnimatorState defaultState = null;
                foreach (string path in clipPaths)
                {
                    var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
                    if (clip == null)
                    {
                        continue;
                    }

                    var state = sm.AddState(clip.name);
                    state.motion = clip;
                    if (defaultState == null)
                    {
                        defaultState = state;
                    }
                }

                if (defaultState != null)
                {
                    sm.defaultState = defaultState;
                }

                EditorUtility.SetDirty(controller);
            }

            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();

            return new ImportResult
            {
                CharacterName = stem,
                TexturePath = textureAssetPath,
                OutputFolder = outFolder,
                ClipPaths = clipPaths,
                ControllerPath = controllerPath
            };
        }
        finally
        {
            _importing = prev;
        }
    }

    internal static bool IsImporting => _importing;

    internal static string ToAbsolutePath(string assetPath)
    {
        string projectRoot = Path.GetDirectoryName(Application.dataPath);
        return Path.GetFullPath(Path.Combine(projectRoot ?? "", assetPath));
    }

    static void EnsureFolder(string assetFolder)
    {
        assetFolder = assetFolder.Replace('\\', '/').TrimEnd('/');
        if (AssetDatabase.IsValidFolder(assetFolder))
        {
            return;
        }

        string[] parts = assetFolder.Split('/');
        string current = parts[0];
        for (int i = 1; i < parts.Length; i++)
        {
            string next = current + "/" + parts[i];
            if (!AssetDatabase.IsValidFolder(next))
            {
                AssetDatabase.CreateFolder(current, parts[i]);
            }

            current = next;
        }
    }

    public class ImportResult
    {
        public string CharacterName;
        public string TexturePath;
        public string OutputFolder;
        public List<string> ClipPaths = new List<string>();
        public string ControllerPath;
    }
}

class FrameforgeSheetPostprocessor : AssetPostprocessor
{
    static void OnPostprocessAllAssets(
        string[] importedAssets,
        string[] deletedAssets,
        string[] movedAssets,
        string[] movedFromAssetPaths)
    {
        if (FrameforgeSheetImport.IsImporting || importedAssets == null || importedAssets.Length == 0)
        {
            return;
        }

        foreach (string path in importedAssets)
        {
            if (path == null || !path.EndsWith("_sheet.png", System.StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            string jsonPath = System.IO.Path.ChangeExtension(path, ".json");
            if (!System.IO.File.Exists(FrameforgeSheetImport.ToAbsolutePath(jsonPath)))
            {
                continue;
            }

            try
            {
                FrameforgeSheetImport.ImportAtPath(path);
                Debug.Log($"Frameforge: auto-imported {path}");
            }
            catch (System.Exception ex)
            {
                Debug.LogWarning($"Frameforge: auto-import skipped for {path}: {ex.Message}");
            }
        }
    }
}
